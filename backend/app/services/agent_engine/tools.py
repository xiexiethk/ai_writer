"""
Agent RAG Engine - 工具定义
封装 4 种 RAG 策略工具和辅助工具为 LangChain Tools
"""
import logging
import datetime
import os
from typing import List, Dict, Optional
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.agent_engine.prompts import (
    STEP_BACK_GENERATION_PROMPT,
    MULTI_QUERY_GENERATION_PROMPT,
    REWRITE_GENERATION_PROMPT,
)
from app.services.agent_engine.llm import create_chat_llm
from app.services.semantic_highlight_service import get_semantic_highlight_service
from app.services.retrieval_helper import search_with_variants
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)

MAX_STEP_BACK_RESULTS = 2
MAX_MULTI_QUERY_RESULTS = 2
MAX_MULTI_QUERY_VARIANTS = 2
MAX_REWRITE_RESULTS = 5
MIN_COMPLEX_QUERY_LEN = 10
MIN_REWRITE_TRIGGER_LEN = 12

# 语义高亮服务实例（懒加载）
_semantic_highlight_service = None


def _get_semantic_highlight_service():
    """获取语义高亮服务实例（单例）"""
    global _semantic_highlight_service
    if _semantic_highlight_service is None:
        _semantic_highlight_service = get_semantic_highlight_service()
    return _semantic_highlight_service

# 工具内部使用的轻量级 LLM（用于生成查询）
_tool_llm = None
_embedding_service = None


def _get_tool_llm():
    """获取工具内部使用的 LLM 实例（单例）"""
    global _tool_llm
    if _tool_llm is None:
        _tool_llm = create_chat_llm(
            provider=os.getenv("AGENT_CHAT_PROVIDER") or "deepseek",
            model=os.getenv("AGENT_CHAT_MODEL"),
            base_url=os.getenv("AGENT_CHAT_BASE_URL"),
            temperature=0.3  # 较低温度以获得更稳定的查询生成
        )
    return _tool_llm


def _get_embedding_service():
    """延迟获取 embedding service，避免模块导入时即发起模型探测。"""
    global _embedding_service
    if _embedding_service is None:
        from app.services.embedding import embedding_service as _service
        _embedding_service = _service
    return _embedding_service


def infer_primary_search_tool(
    query: str,
    chat_history: Optional[List[Dict]] = None,
    document_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """根据问题结构推断首个检索工具，尽量少依赖固定匹配词。"""
    text = (query or "").strip()
    if not text or not document_ids:
        return None

    # 有上下文依赖时，先重写再搜。
    if should_use_rewrite_search(text, chat_history):
        return "t_rewrite_search"

    # 明显多子句 / 多维问题，考虑多路检索。
    if should_use_multi_query_search(text):
        return "t_multi_query_search"

    # 明显长问题且更像宏观解释时，才考虑回溯检索。
    if should_use_step_back_search(text):
        return "t_step_back_search"

    return "t_direct_search"


def _execute_search_with_results(
    query: str,
    top_k: int = 5,
    document_ids: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    original_question: Optional[str] = None
) -> tuple[str, List[Dict]]:
    """
    执行底层搜索并返回格式化和原始结果
    
    Args:
        query: 查询文本
        top_k: 返回结果数量
        document_ids: 限制搜索范围的文档ID列表
    
    Returns:
        (formatted_text, raw_results) 元组
        - formatted_text: 格式化的搜索结果文本
        - raw_results: 原始搜索结果列表
    """
    try:
        if user_id is None:
            logger.warning("Agent 检索缺少 user_id，上下文隔离无法生效")
            return "搜索失败: 缺少用户上下文，无法访问知识库。", []

        if not vector_store.connected:
            vector_store.connect()
        
        # 执行搜索
        if document_ids is not None and not document_ids:
            return "未找到相关文档。", []

        unique_doc_ids = list(dict.fromkeys(document_ids)) if document_ids is not None else None
        results = search_with_variants(
            query=query,
            top_k=top_k,
            user_id=user_id,
            extra_queries=[original_question] if original_question and original_question != query else None,
            search_fn=lambda search_query: _search_standard_vector_store(
                search_query,
                top_k=top_k,
                document_ids=unique_doc_ids,
            )
        )
        
        # 格式化结果为文本
        if not results:
            return "未找到相关文档。", []
        
        # 获取语义高亮服务
        highlight_service = _get_semantic_highlight_service()
        logger.info(f"语义高亮服务状态: available={highlight_service.is_available()}, enabled={highlight_service.enabled}")
        
        formatted_parts = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "无标题")
            content = result.get("content", "")
            score = result.get("score", 0)
            doc_id = result.get("document_id", "未知")
            
            # 对每个文档块进行语义高亮处理
            highlighted_content = content  # 默认使用原始内容
            try:
                if highlight_service.is_available() and content:
                    logger.debug(f"开始对文档块 {i} 进行语义高亮处理，查询: {query[:50]}...")
                    highlight_result = highlight_service.highlight(
                        query=query,
                        context=content
                    )
                    
                    # 将高亮结果添加到文档块字典中
                    highlighted_sentences = highlight_result.get("highlighted_sentences", [])
                    sentence_probabilities = highlight_result.get("sentence_probabilities", [])
                    compression_rate = highlight_result.get("compression_rate", 0.0)
                    
                    result["highlighted_sentences"] = highlighted_sentences
                    result["sentence_probabilities"] = sentence_probabilities
                    result["compression_rate"] = compression_rate
                    
                    # 如果有高亮句子，优先使用高亮句子；否则使用原始内容
                    if highlighted_sentences:
                        # 将高亮句子用换行符连接，形成高亮后的内容
                        highlighted_content = "\n".join(highlighted_sentences)
                        logger.debug(
                            f"文档块 {i} 语义高亮完成: "
                            f"原始长度={len(content)}, "
                            f"高亮句子数={len(highlighted_sentences)}, "
                            f"压缩率={compression_rate:.2%}"
                        )
                    else:
                        logger.debug(f"文档块 {i} 未找到高亮句子，使用原始内容")
                else:
                    # 语义高亮不可用，使用原始内容
                    result["highlighted_sentences"] = []
                    result["sentence_probabilities"] = []
                    result["compression_rate"] = 0.0
            except Exception as e:
                # 高亮处理失败，降级使用原始内容
                logger.warning(f"文档块 {i} 语义高亮处理失败: {e}，使用原始内容")
                result["highlighted_sentences"] = []
                result["sentence_probabilities"] = []
                result["compression_rate"] = 0.0
            
            # 格式化输出：优先使用高亮内容
            display_content = highlighted_content if highlighted_content else content
            
            formatted_parts.append(
                f"[引用{i}] 文档: {doc_id}\n"
                f"标题: {title}\n"
                f"相关性: {score:.4f}\n"
                f"内容: {display_content}\n"
                f"---"
            )
        
        formatted_text = "\n\n".join(formatted_parts)
        return formatted_text, results
    
    except Exception as e:
        logger.error(f"执行搜索失败: {e}")
        return f"搜索失败: {str(e)}", []


def _search_standard_vector_store(
    query: str,
    top_k: int,
    document_ids: Optional[List[str]] = None,
) -> List[Dict]:
    """在标准向量表 document_chunks_v2 中搜索。"""
    if not vector_store.connected:
        vector_store.connect()

    query_vector = _get_embedding_service().encode_single(query)
    unique_doc_ids = list(dict.fromkeys(document_ids or []))
    if not unique_doc_ids:
        logger.warning("Agent 标准向量检索缺少 document_ids，拒绝执行全库检索")
        return []
    if unique_doc_ids:
        all_results: List[Dict] = []
        per_doc_k = max(top_k // max(len(unique_doc_ids), 1), 3)
        for doc_id in unique_doc_ids:
            try:
                all_results.extend(vector_store.search(query_vector, per_doc_k, doc_id))
            except Exception as exc:
                logger.warning("Agent 标准向量检索文档 %s 失败: %s", doc_id, exc)
        all_results.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return all_results[:top_k]


def _execute_search(
    query: str,
    top_k: int = 5,
    document_ids: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    original_question: Optional[str] = None
) -> str:
    """
    执行底层搜索并格式化结果（向后兼容）
    
    Args:
        query: 查询文本
        top_k: 返回结果数量
        document_ids: 限制搜索范围的文档ID列表
    
    Returns:
        格式化的搜索结果文本
    """
    formatted_text, _ = _execute_search_with_results(query, top_k, document_ids, user_id, original_question)
    return formatted_text


@tool
def t_direct_search(
    query: str,
    document_ids: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    original_question: Optional[str] = None
) -> str:
    """
    直接搜索工具。用于简单、直接的事实性问题检索。
    
    Args:
        query: 查询文本
        document_ids: 限制搜索范围的文档ID列表（可选）
    
    Returns:
        搜索结果文本（格式化后的字符串）
    """
    formatted_text, _ = _execute_search_with_results(
        query,
        top_k=6,
        document_ids=document_ids,
        user_id=user_id,
        original_question=original_question
    )
    return formatted_text


@tool
def t_step_back_search(
    query: str,
    document_ids: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    original_question: Optional[str] = None
) -> str:
    """
    Step-Back 搜索工具。用于需要背景知识或原理性解释的问题。
    工具会自动生成抽象问题并进行搜索，同时搜索原始问题。
    
    Args:
        query: 查询文本
        document_ids: 限制搜索范围的文档ID列表（可选）
    
    Returns:
        合并的搜索结果文本（背景知识 + 具体细节）
    """
    try:
        normalized_query = (query or "").strip()
        if len(normalized_query) < 4 and not original_question:
            return "问题过于简短，建议先补充上下文后再检索。"
        # 1. 生成抽象问题
        llm = _get_tool_llm()
        chain = ChatPromptTemplate.from_template(STEP_BACK_GENERATION_PROMPT) | llm | StrOutputParser()
        abstract_query = chain.invoke({"question": query}).strip()
        
        logger.info(f"Step-Back 抽象问题: {abstract_query}")
        
        # 2. 执行两次搜索（获取原始结果）
        res_abstract_text, res_abstract_raw = _execute_search_with_results(
            abstract_query,
            top_k=MAX_STEP_BACK_RESULTS,
            document_ids=document_ids,
            user_id=user_id,
            original_question=original_question
        )
        res_concrete_text, res_concrete_raw = _execute_search_with_results(
            query,
            top_k=MAX_STEP_BACK_RESULTS,
            document_ids=document_ids,
            user_id=user_id,
            original_question=original_question
        )
        
        # 3. 合并结果（格式化文本）
        formatted_result = (
            f"【背景知识 (基于抽象问题: {abstract_query})】:\n{res_abstract_text}\n\n"
            f"【具体细节 (基于原始问题: {query})】:\n{res_concrete_text}"
        )
        
        return formatted_result
    except Exception as e:
        logger.error(f"Step-Back 搜索失败: {e}")
        # 降级为直接搜索
        formatted_text, _ = _execute_search_with_results(
            query,
            top_k=5,
            document_ids=document_ids,
            user_id=user_id,
            original_question=original_question
        )
        return formatted_text


@tool
def t_multi_query_search(
    query: str,
    document_ids: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    original_question: Optional[str] = None
) -> str:
    """
    多查询搜索工具。用于复杂问题或单一关键词可能不准确的情况。
    工具会自动从不同角度生成3个查询并并行搜索。
    
    Args:
        query: 查询文本
        document_ids: 限制搜索范围的文档ID列表（可选）
    
    Returns:
        合并的搜索结果文本
    """
    try:
        normalized_query = (query or "").strip()
        if len(normalized_query) < 4:
            return "问题过于简短，建议直接使用关键词检索。"
        # 1. 生成多个查询
        llm = _get_tool_llm()
        chain = ChatPromptTemplate.from_template(MULTI_QUERY_GENERATION_PROMPT) | llm | StrOutputParser()
        queries_str = chain.invoke({"question": query}).strip()
        
        # 解析查询列表
        queries = [q.strip() for q in queries_str.split('\n') if q.strip()]
        if not queries:
            queries = [query]  # 如果生成失败，使用原始查询
        
        logger.info(f"Multi-Query 生成的查询: {queries}")
        
        # 2. 执行多个搜索（每个查询返回较少结果，然后合并）
        all_results_parts = []
        for i, q in enumerate(queries[:MAX_MULTI_QUERY_VARIANTS], 1):  # 最多2个查询
            res_text, _ = _execute_search_with_results(
                q,
                top_k=MAX_MULTI_QUERY_RESULTS,
                document_ids=document_ids,
                user_id=user_id,
                original_question=original_question
            )
            all_results_parts.append(f"【视角{i}: {q}】:\n{res_text}")
        
        return "\n\n".join(all_results_parts)
    except Exception as e:
        logger.error(f"Multi-Query 搜索失败: {e}")
        # 降级为直接搜索
        formatted_text, _ = _execute_search_with_results(
            query,
            top_k=5,
            document_ids=document_ids,
            user_id=user_id,
            original_question=original_question
        )
        return formatted_text


@tool
def t_rewrite_search(
    query: str, 
    document_ids: Optional[List[str]] = None,
    chat_history: Optional[List[Dict]] = None,
    user_id: Optional[int] = None,
    original_question: Optional[str] = None
) -> str:
    """
    重写搜索工具。用于用户输入模糊、包含指代词（如'它'）或有拼写错误的情况。
    工具会自动优化查询词后进行搜索。
    
    Args:
        query: 查询文本
        document_ids: 限制搜索范围的文档ID列表（可选）
        chat_history: 对话历史记录（可选），格式为 [{"role": "user", "content": "..."}, ...]
    
    Returns:
        搜索结果文本
    """
    try:
        normalized_query = (query or "").strip()
        if not chat_history and len(normalized_query) < 4:
            return "问题过于简短，建议补充上下文后再重写检索。"
        # 1. 格式化对话历史
        history_str = ""
        if chat_history:
            history_parts = []
            for msg in chat_history[-10:]:  # 只保留最近10条消息
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    history_parts.append(f"[User: {content}]")
                elif role == "assistant":
                    history_parts.append(f"[AI: {content}]")
            history_str = "\n".join(history_parts)
        
        # 2. 重写查询（结合对话历史）
        llm = _get_tool_llm()
        chain = ChatPromptTemplate.from_template(REWRITE_GENERATION_PROMPT) | llm | StrOutputParser()
        new_query = chain.invoke({
            "question": query,
            "chat_history": history_str
        }).strip()
        
        if not new_query:
            new_query = query  # 如果生成失败，使用原始查询
        
        logger.info(f"Rewrite 重写后的查询: {new_query} (原始: {query})")
        
        # 3. 使用重写后的查询执行搜索
        results_text, _ = _execute_search_with_results(
            new_query,
            top_k=MAX_REWRITE_RESULTS,
            document_ids=document_ids,
            user_id=user_id,
            original_question=original_question
        )
        return f"【重写后的查询: {new_query}】\n\n{results_text}"
    except Exception as e:
        logger.error(f"Rewrite 搜索失败: {e}")
        # 降级为直接搜索
        formatted_text, _ = _execute_search_with_results(
            query,
            top_k=MAX_REWRITE_RESULTS,
            document_ids=document_ids,
            user_id=user_id,
            original_question=original_question
        )
        return formatted_text


def should_use_rewrite_search(query: str, chat_history: Optional[List[Dict]] = None) -> bool:
    """判断是否需要重写检索。"""
    text = (query or "").strip()
    if not text:
        return False
    if len(text) < MIN_REWRITE_TRIGGER_LEN:
        return True
    if chat_history:
        return True
    # 尽量少依赖固定词；只对明显指代/上下文依赖做保守判断。
    return any(token in text for token in ("它", "这个", "那个", "上述", "前文", "前者", "后者"))


def should_use_step_back_search(query: str) -> bool:
    """判断是否需要 step-back 检索。"""
    text = (query or "").strip()
    if len(text) < MIN_COMPLEX_QUERY_LEN:
        return False
    # 优先用结构特征：长问题 + 多分句，才考虑回溯检索
    clause_separators = ("，", "；", "。", "、")
    clause_count = sum(text.count(sep) for sep in clause_separators)
    if clause_count >= 2:
        return True
    return any(marker in text for marker in ("原理", "背景", "演变", "发展", "机制", "体系", "框架", "影响", "原因"))


def should_use_multi_query_search(query: str) -> bool:
    """判断是否需要多路检索。"""
    text = (query or "").strip()
    if len(text) < MIN_COMPLEX_QUERY_LEN:
        return False
    # 优先用结构特征：多子句、多并列项，再考虑多路检索
    clause_markers = ("、", "；", "分别", "对比", "比较", "差异", "异同")
    if any(marker in text for marker in clause_markers):
        return True
    clause_count = sum(text.count(sep) for sep in ("，", "；", "。"))
    return clause_count >= 2


def build_agent_toolset(
    query: str,
    chat_history: Optional[List[Dict]] = None,
    document_ids: Optional[List[str]] = None,
) -> List:
    """根据问题特征构建 Agent 本轮可用工具集合，避免所有工具同时暴露。"""
    base_tools = [calculator, get_current_time]
    if not document_ids:
        return base_tools

    normalized_query = (query or "").strip()
    if should_use_rewrite_search(normalized_query, chat_history):
        return [t_rewrite_search, t_direct_search, *base_tools]
    if should_use_multi_query_search(normalized_query):
        return [t_multi_query_search, t_direct_search, *base_tools]
    if should_use_step_back_search(normalized_query):
        return [t_step_back_search, t_direct_search, *base_tools]
    return [t_direct_search, *base_tools]


@tool
def calculator(expression: str) -> str:
    """
    计算数学表达式。例如 '2 * 3 + 5' 或 'sqrt(16)'
    
    Args:
        expression: 数学表达式字符串
    
    Returns:
        计算结果
    """
    try:
        # 安全的数学计算（只允许基本数学运算）
        allowed_names = {
            k: v for k, v in __builtins__.items() if k in ['abs', 'round', 'min', 'max', 'sum']
        }
        allowed_names.update({
            'sqrt': lambda x: x ** 0.5,
            'pow': pow,
        })
        
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"计算错误: {str(e)}"


@tool
def get_current_time() -> str:
    """
    获取当前的系统时间，格式为 ISO 8601
    
    Returns:
        当前时间字符串
    """
    return datetime.datetime.now().isoformat()


# 导出工具列表
AGENT_TOOLS = [
    t_direct_search,
    t_step_back_search,
    t_multi_query_search,
    t_rewrite_search,
    calculator,
    get_current_time,
]
