"""
文档生成服务
处理大纲生成、内容生成和Word导出
"""
import logging
from typing import List, Dict, Optional
import json
import re
import uuid
from datetime import datetime
import time
from sqlalchemy import select

from app.services.llm_gateway import (
    chat_completion_async,
    resolve_chat_model,
    resolve_chat_provider,
)
from app.services.rag import rag_service  # 保留但不使用
from app.services.hybrid_rag_service import hybrid_rag_service
from app.services.agent_engine.service import agent_rag_service  # 大纲生成仍可能使用
from app.models.document import storage
from app.core.database import AsyncSessionLocal
from app.models.document_db import Document

logger = logging.getLogger(__name__)


class DocumentGeneratorService:
    """文档生成服务"""

    def __init__(
        self,
        provider: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        self.provider = resolve_chat_provider(provider)
        self.llm_model = resolve_chat_model(self.provider, llm_model)

    def _format_agent_sources_for_context(self, sources: List[Dict], max_chunks: int = 3) -> str:
        """
        将 Agent 检索返回的 sources 格式化为 context 字符串（用于大纲生成）
        
        Args:
            sources: Agent 返回的 sources 列表
            max_chunks: 最大使用的文档块数量
        
        Returns:
            格式化后的 context 字符串
        """
        if not sources:
            return ""
        
        context_parts = []
        for i, source in enumerate(sources[:max_chunks], 1):
            title = source.get("title", "无标题")
            content = source.get("content", "")
            context_parts.append(f"[参考{i}] {title}\n{content[:500]}...")
        
        return "\n\n".join(context_parts)

    def _format_agent_sources_for_content(self, sources: List[Dict], min_score: float = 0.3) -> List[Dict]:
        """
        将 Agent 检索返回的 sources 格式化为内容生成所需的 sources 格式
        
        Args:
            sources: Agent 返回的 sources 列表
            min_score: 最小相似度阈值
        
        Returns:
            格式化后的 sources 列表
        """
        formatted_sources = []
        for source in sources:
            score = source.get("score", 0)
            if score > min_score:
                formatted_sources.append({
                    "id": source.get("id", ""),
                    "document_id": source.get("document_id", ""),
                    "document_name": source.get("document_name", "未知文档"),
                    "title": source.get("title", ""),
                    "content": source.get("content", ""),
                    "score": score
                })
        
        return formatted_sources

    async def _decorate_retrieved_sources(self, sources: List[Dict]) -> List[Dict]:
        """为直接检索结果补全文档名，适配内容生成 source 结构。"""
        if not sources:
            return []

        doc_ids = {item.get("document_id") for item in sources if item.get("document_id")}
        doc_names: Dict[str, str] = {}
        if doc_ids:
            async with AsyncSessionLocal() as db:
                rows = await db.execute(
                    select(Document.id, Document.title).where(Document.id.in_(list(doc_ids)))
                )
                doc_names = {row[0]: row[1] for row in rows.all()}

        return [
            {
                "id": source.get("id", ""),
                "document_id": source.get("document_id", ""),
                "document_name": doc_names.get(source.get("document_id", ""), "未知文档"),
                "title": source.get("title", ""),
                "content": source.get("content", ""),
                "score": source.get("score", 0),
            }
            for source in sources
        ]

    async def _resolve_document_ids(
        self,
        folder_ids: List[str],
        user_id: Optional[int] = None,
    ) -> List[str]:
        """优先按当前用户过滤知识库文档，兼容旧的本地存储回退。"""
        if not folder_ids:
            return []

        if user_id is not None:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Document.id).where(
                        Document.user_id == user_id,
                        Document.parsed == True,
                        Document.folder_id.in_(folder_ids),
                    )
                )
                return [row[0] for row in result.all()]

        all_document_ids: List[str] = []
        for folder_id in folder_ids:
            documents, _ = storage.list_documents(folder=folder_id)
            all_document_ids.extend([doc["id"] for doc in documents])
        return all_document_ids

    async def generate_outline(
        self,
        topic: str,
        folder_ids: List[str],
        user_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        生成文档大纲

        Args:
            topic: 研究主题
            folder_ids: 知识库ID列表

        Returns:
            树形大纲结构
        """
        try:
            start_ts = time.perf_counter()
            # 1. 获取所有文档ID
            all_document_ids = await self._resolve_document_ids(folder_ids, user_id=user_id)
            logger.info("大纲生成开始: topic=%s, folder_count=%s, doc_count=%s", topic, len(folder_ids), len(all_document_ids))

            # 2. 使用轻量直接检索相关内容
            context = ""
            if all_document_ids:
                logger.info("大纲生成使用直接检索，从 %s 个文档中检索相关内容", len(all_document_ids))

                query = f"{topic}\n核心内容 综述 大纲 主题"
                sources = await hybrid_rag_service.hybrid_search(
                    query=query,
                    user_id=user_id,
                    document_ids=all_document_ids,
                    top_k=6,
                    mode="outline",
                )
                context = self._format_agent_sources_for_context(sources, max_chunks=3)
                logger.info("大纲生成直接检索到 %s 个相关片段，用于生成大纲", len(sources))

            # 3. 构建提示词 - 使用 Markdown 格式而不是 JSON
            if context:
                prompt = f"""请基于以下知识库参考资料，为主题"{topic}"生成一个详细的文档大纲。

【重要要求】
1. 大纲内容必须严格基于上述知识库参考资料，不得脱离资料范围
2. 大纲要层次分明，使用多级标题（最多3级）
3. 使用 Markdown 格式，# 号表示标题层级
4. 第一层用 ## 表示章节，第二层用 ### 表示小节，第三层用 - 表示要点
5. 【层级关联】子标题的内容范围必须严格隶属于其父标题，不得超出父标题的主题范畴
   - 例如：父标题是"军事法规"，子标题必须是军事法规下的具体内容，如"适用范围"、"处罚措施"等
   - 严禁子标题涉及与父标题无关的内容
6. 【一致性】确保同级章节之间逻辑连贯，避免内容重复
7. 请确保大纲全面且逻辑清晰，涵盖知识库资料中的所有要点

知识库参考资料：
{context}

返回格式示例：
## 第一章 绪论
### 1.1 研究背景
- 背景要点1
- 背景要点2
### 1.2 研究意义
- 理论意义
- 实践意义

## 第二章 核心概念
### 2.1 基本概念
- 概念1
- 概念2

请只返回大纲内容，不要包含其他解释文字。"""
            else:
                prompt = f"""请为主题"{topic}"生成一个详细的文档大纲。

【注意】由于未提供知识库参考资料，请根据通用知识生成大纲，但请注意：
1. 大纲要层次分明，使用多级标题（最多3级）
2. 使用 Markdown 格式，# 号表示标题层级
3. 第一层用 ## 表示章节，第二层用 ### 表示小节，第三层用 - 表示要点
4. 【层级关联】子标题的内容范围必须严格隶属于其父标题，不得超出父标题的主题范畴
5. 请确保大纲全面且逻辑清晰

返回格式示例：
## 第一章 绪论
### 1.1 研究背景
- 背景要点1
- 背景要点2
### 1.2 研究意义
- 理论意义
- 实践意义

## 第二章 核心概念
### 2.1 基本概念
- 概念1
- 概念2

请只返回大纲内容，不要包含其他解释文字。"""

            # 4. 调用LLM生成大纲
            content = await chat_completion_async(
                provider=self.provider,
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业的文档大纲生成助手，擅长基于知识库资料创建结构清晰、逻辑严密的文档大纲。

【核心原则】
1. 必须严格基于提供的知识库资料生成大纲，不得脱离资料范围
2. 确保父子章节之间有明确的层级关联性，子章节必须隶属于父章节的主题范畴
3. 子章节是对父章节的深入展开，不得超出父章节范围"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                top_p=0.9,
                max_tokens=2000,
                timeout=120.0,
            )

            # 5. 解析 Markdown 格式的大纲
            outline = self._parse_outline_markdown(content)

            # 6. 为每个节点生成唯一ID
            outline = self._ensure_outline_ids(outline)

            logger.info(
                "大纲生成成功，包含 %s 个节点，耗时 %.2fs",
                self._count_outline_nodes(outline),
                time.perf_counter() - start_ts,
            )
            return outline

        except Exception as e:
            logger.error(f"大纲生成失败: {e}")
            raise

    def _parse_outline_markdown(self, content: str) -> List[Dict]:
        """解析 Markdown 格式的大纲"""
        logger.info(f"Markdown 内容:\n{content[:2000]}...")

        # 移除可能的 markdown 代码块标记
        if "```markdown" in content:
            content = content.split("```markdown")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        lines = content.strip().split('\n')
        outline = []
        stack = []  # (node_dict, level)
        node_counter = [0]  # 使用列表作为可变计数器，方便在嵌套函数中更新

        for line in lines:
            line = line.rstrip()
            if not line:
                continue

            # 跳过单独的 ---
            if line.strip() == '---':
                continue

            # 检测标题级别
            level = 0
            label = None

            if line.startswith('## '):
                level = 1  # 章节
                label = line[3:].strip()
            elif line.startswith('### '):
                level = 2  # 小节
                label = line[4:].strip()
            elif line.startswith('#### '):
                level = 3  # 要点
                label = line[5:].strip()
            elif line.startswith('- ') or line.startswith('* '):
                level = 3  # 要点（列表项）
                label = line[2:].strip()
            elif re.match(r'^\d+\.', line):
                # 数字开头的行，可能是章节
                level = 1
                label = line.strip()
            elif re.match(r'^\d+\.\d+\.', line):
                # 数字.数字 开头的行，可能是小节
                level = 2
                label = line.strip()
            else:
                # 其他行，如果是缩进的，可能是要点
                if line.startswith('    '):
                    level = 3
                    label = line.strip()
                else:
                    # 尝试作为章节处理
                    level = 1
                    label = line.strip()

            if not label:
                continue

            # 创建节点 - 使用全局计数器确保唯一性
            node_counter[0] += 1
            node = {
                "id": f"node-{node_counter[0]}",
                "label": label,
                "children": []
            }

            # 根据层级找到父节点
            while stack and stack[-1][1] >= level:
                stack.pop()

            if stack:
                stack[-1][0]["children"].append(node)
            else:
                outline.append(node)

            stack.append((node, level))

        logger.info(f"解析后的大纲节点数: {len(outline)}")
        return outline

    def _parse_outline_json(self, content: str) -> List[Dict]:
        """解析大纲JSON"""
        # 尝试提取JSON
        content = content.strip()

        logger.info(f"原始内容 (前2000字符):\n{content[:2000]}...")

        # 移除可能的markdown代码块标记
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        # 尝试找到JSON对象/数组的开始和结束
        json_start = -1
        json_end = -1

        # 找到第一个 { 或 [
        for i, char in enumerate(content):
            if char in ['{', '[']:
                json_start = i
                break

        if json_start >= 0:
            # 从这里开始，找到匹配的结束符
            stack = []
            start_char = content[json_start]
            end_char = '}' if start_char == '{' else ']'
            matching = {'{': '}', '[': ']', '}': '{', ']': '['}

            for i in range(json_start, len(content)):
                char = content[i]
                if char in ['{', '[']:
                    stack.append(char)
                elif char in ['}', ']']:
                    if stack and matching.get(stack[-1]) == char:
                        stack.pop()
                        if not stack:
                            json_end = i + 1
                            break

            if json_end > json_start:
                content = content[json_start:json_end]

        logger.info(f"提取后的JSON (前2000字符):\n{content[:2000]}...")

        # 尝试修复常见的JSON问题
        content = self._fix_json(content)

        # 尝试解析JSON
        try:
            outline = json.loads(content)

            # 如果是对象（单个根节点），转换为数组
            if isinstance(outline, dict):
                # 如果根节点有children，直接使用children
                if "children" in outline:
                    return outline["children"]
                # 否则包装成数组
                return [outline]

            if isinstance(outline, list):
                return outline

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"错误位置附近的内容: {content[max(0, e.pos-200):e.pos+200]}")
            # 最后尝试使用文本解析
            logger.warning("尝试使用文本解析作为容错方案")
            return self._parse_outline_from_text(content)

    def _fix_json(self, json_str: str) -> str:
        """尝试修复常见的JSON格式问题"""
        # 移除控制字符（除了换行、制表符等）
        json_str = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', json_str)

        # 尝试修复未转义的换行符在字符串中
        # 这是一个常见问题，LLM经常在label中包含换行
        lines = json_str.split('\n')
        fixed_lines = []
        in_string = False
        escape_next = False

        for line in lines:
            fixed_line = []
            for char in line:
                if escape_next:
                    fixed_line.append(char)
                    escape_next = False
                    continue

                if char == '\\':
                    fixed_line.append(char)
                    escape_next = True
                elif char == '"' and not escape_next:
                    in_string = not in_string
                    fixed_line.append(char)
                elif char == '\n' and in_string:
                    # 在字符串中的换行，替换为 \\n
                    fixed_line.append('\\n')
                elif char == '\t' and in_string:
                    # 在字符串中的制表符，替换为 \\t
                    fixed_line.append('\\t')
                else:
                    fixed_line.append(char)

            fixed_lines.append(''.join(fixed_line))

        return '\n'.join(fixed_lines)

    def _parse_outline_from_text(self, text: str) -> List[Dict]:
        """从文本中解析大纲结构（容错方案）"""
        lines = text.strip().split("\n")
        outline = []
        stack = []  # (node, level)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测标题级别
            level = 0
            if line.startswith("# "):
                level = 1
                label = line[2:].strip()
            elif line.startswith("## "):
                level = 2
                label = line[3:].strip()
            elif line.startswith("### "):
                level = 3
                label = line[4:].strip()
            elif line.startswith("#### "):
                level = 4
                label = line[5:].strip()
            elif re.match(r"^\d+\.", line):
                # 1. 章节标题
                level = 1
                label = line
            elif re.match(r"^\d+\.\d+\.", line):
                # 1.1 小节标题
                level = 2
                label = line
            elif re.match(r"^\d+\.\d+\.\d+\.", line):
                # 1.1.1 要点
                level = 3
                label = line
            elif line.startswith("- ") or line.startswith("• "):
                # 列表项
                level = 3
                label = line[2:].strip()
            else:
                # 默认级别
                level = 1
                label = line

            node = {
                "id": f"section-{len(outline)}-{level}",
                "label": label,
                "children": []
            }

            # 根据层级找到父节点
            while stack and stack[-1][1] >= level:
                stack.pop()

            if stack:
                stack[-1][0]["children"].append(node)
            else:
                outline.append(node)

            stack.append((node, level))

        return outline

    def _ensure_outline_ids(self, outline: List[Dict], parent_id: str = "") -> List[Dict]:
        """确保大纲节点有唯一ID"""
        for i, node in enumerate(outline):
            if not node.get("id"):
                node["id"] = f"{parent_id}section-{i}" if parent_id else f"section-{i}"

            if node.get("children"):
                node["children"] = self._ensure_outline_ids(
                    node["children"],
                    f"{node['id']}-"
                )

        return outline

    def _count_outline_nodes(self, outline: List[Dict]) -> int:
        """统计大纲节点数量"""
        count = 0
        for node in outline:
            count += 1
            if node.get("children"):
                count += self._count_outline_nodes(node["children"])
        return count

    async def generate_section_content(
        self,
        section_title: str,
        section_id: str,
        document_ids: List[str],
        context_sections: List[str] = None,
        custom_prompt: str = None,
        full_outline: List[Dict] = None,
        user_id: Optional[int] = None,
    ) -> Dict:
        """
        生成章节内容

        Args:
            section_title: 章节标题
            section_id: 章节ID
            document_ids: 知识库文档ID列表
            context_sections: 上下文章节（父级章节标题列表）
            custom_prompt: 自定义生成需求
            full_outline: 完整大纲结构（用于上下文理解）

        Returns:
            生成的内容和引用
        """
        try:
            start_ts = time.perf_counter()
            # 1. 构建查询（包含上下文）
            query = section_title
            if context_sections:
                query = " > ".join(context_sections + [section_title])

            # 2. 使用轻量直接检索相关内容
            sources = []
            if document_ids:
                logger.info("章节内容生成使用直接检索: section=%s, doc_count=%s", section_title, len(document_ids))

                retrieval_query = section_title
                if context_sections:
                    retrieval_query = " > ".join(context_sections + [section_title])
                retrieval_query = f"{retrieval_query}\n章节内容 综述 写作 要点"

                raw_sources = await hybrid_rag_service.hybrid_search(
                    query=retrieval_query,
                    user_id=user_id,
                    document_ids=document_ids,
                    top_k=6,
                    mode="section",
                )

                decorated_sources = await self._decorate_retrieved_sources(raw_sources)
                sources = self._format_agent_sources_for_content(decorated_sources, min_score=0.25)

                logger.info("章节直接检索到 %s 个片段，保留 %s 个高相似度片段", len(raw_sources), len(sources))

            # 3. 构建提示词
            prompt = self._build_content_prompt(section_title, sources, context_sections, custom_prompt, full_outline)

            # 4. 调用 LLM 生成内容
            content = await chat_completion_async(
                provider=self.provider,
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业的文档写作助手，擅长严格基于知识库资料撰写结构清晰、内容丰富的文档章节。

【核心原则】
1. 【知识库唯一】撰写内容时，只能使用提供的知识库资料
2. 【允许展开】可在知识库资料基础上进行合理分析、推断和逻辑延伸
3. 【禁止外部】严禁使用任何知识库之外的通用知识、外部信息或预训练数据
4. 【父子关联】子章节内容必须隶属于父章节主题，不得超出范畴"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                top_p=0.9,
                max_tokens=1200,
                timeout=240.0,
            )

            logger.info(
                "章节 '%s' 内容生成完成，字数: %s，耗时 %.2fs",
                section_title,
                len(content),
                time.perf_counter() - start_ts,
            )

            return {
                "paragraph_id": str(uuid.uuid4()),
                "section_id": section_id,
                "content": content,
                "sources": sources,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"生成章节内容失败: {e}")
            raise

    async def regenerate_paragraph(
        self,
        section_title: str,
        section_id: str,
        document_ids: List[str],
        context_sections: List[str] = None,
        custom_prompt: str = None,
        full_outline: List[Dict] = None,
        user_id: Optional[int] = None,
    ) -> Dict:
        """
        重新生成段落（用于段落重新生成功能）

        与 generate_section_content 相同，但明确为重新生成场景
        """
        return await self.generate_section_content(
            section_title=section_title,
            section_id=section_id,
            document_ids=document_ids,
            context_sections=context_sections,
            custom_prompt=custom_prompt,
            full_outline=full_outline,
            user_id=user_id,
        )

    def _build_content_prompt(
        self,
        section_title: str,
        sources: List[Dict],
        context_sections: List[str] = None,
        custom_prompt: str = None,
        full_outline: List[Dict] = None
    ) -> str:
        """构建内容生成提示词"""
        # 构建上下文路径
        context_path = ""
        parent_section = ""
        if context_sections:
            context_path = " > ".join(context_sections + [section_title])
            parent_section = context_sections[-1] if context_sections else ""
        else:
            context_path = section_title

        # 构建参考资料部分
        reference = ""
        if sources:
            # 有参考资料时，强调只能使用知识库内容
            reference_parts = []
            for i, source in enumerate(sources, 1):
                similarity_percent = source.get('score', 0) * 100
                reference_parts.append(f"""
参考来源 {i}（相似度: {similarity_percent:.1f}%）：
文档：{source['document_name']}
章节：{source['title']}
内容：{source['content'][:800]}
""")

            reference = "知识库参考资料：\n" + "\n".join(reference_parts)
            reference += "\n\n【重要】撰写本章内容时，请完全基于上述知识库资料，可在此基础上合理展开和深入分析，但严禁使用知识库之外的通用知识或外部信息。"
        else:
            reference = "知识库参考资料：未找到相关资料\n\n【警告】当前知识库中没有与该章节相关的内容。由于知识库资料不足，无法生成高质量内容。建议：\n1. 检查知识库中是否包含相关文档\n2. 调整章节标题使其更符合知识库内容\n3. 或在知识库中添加更多相关资料后再生成内容"

        # 构建完整大纲文本（用于上下文）
        outline_text = ""
        if full_outline:
            outline_text = "\n完整文档大纲：\n" + self._format_outline_for_prompt(full_outline)
            logger.info(f"为章节生成提供完整大纲，共 {self._count_outline_nodes(full_outline)} 个章节")

        # 核心撰写要求 - 强调只能使用知识库内容
        requirements = """【核心原则】
1. 【仅限知识库】
   - 撰写本章内容时，必须完全基于上述知识库参考资料
   - 可在知识库资料基础上进行合理展开、深入分析和逻辑推理
   - 【严禁】使用任何知识库之外的通用知识、外部信息或预训练数据
   - 【严禁】编造或添加知识库中不存在的具体事实、数据、案例或引用

2. 【父子层级关联】
   - 当前章节 "{section_title}" 的内容必须严格隶属于其父章节 "{parent_section}" 的主题范围
   - 子章节内容是对父章节的深入展开和细化，不得超出父章节的主题范畴
   - 例如：父章节是"军事法规"，子章节内容必须是军事法规的具体方面（如适用范围、执行标准等）
   - 保持父子章节之间的逻辑连贯性和内容一致性

3. 【内容展开规范】
   - 充分整合参考资料中的信息，对关键点进行深入分析
   - 可以基于知识库资料进行合理推断、归纳总结和逻辑延伸
   - 可以补充知识库资料中隐含的逻辑关系和推导过程
   - 绝不添加知识库资料中完全没有依据的信息

4. 【结构要求】
   - 使用清晰的段落结构，逻辑严密
   - 字数控制在 500-1000 字
   - 不要包含章节标题本身

5. 【引用规范】
   - 如果内容中需要引用其他章节，请严格参考上述"完整文档大纲"，只引用实际存在的章节
   - 不要编造或引用不存在的章节号或章节名

6. 【格式要求】
   - 每段开头必须添加两个全角空格（　　），段落之间不要空行，所有段落紧密排列
   - 如果内容涉及数学公式、科学符号或专业表达式，请使用 LaTeX 格式编写：
     * 行内公式使用单个 $ 符号，例如：$E = mc^2$
     * 独立公式使用双 $ 符号，例如：$$f(x) = \\int_{-\\infty}^{\\infty} e^{-x^2} dx$$
     * 常用数学符号：\\alpha（α）、\\beta（β）、\\sum（求和）、\\int（积分）、\\frac{a}{b}（分数）等"""

        # 如果有自定义需求，添加到要求中
        if custom_prompt and custom_prompt.strip():
            requirements = f"""{requirements}

7. 【特殊要求】
   {custom_prompt.strip()}"""

        prompt = f"""请为文档的以下章节撰写内容：

章节路径：{context_path}
{outline_text}

{reference}

撰写要求：
{requirements}

请撰写内容："""

        return prompt

    def _format_outline_for_prompt(self, outline: List[Dict], indent: int = 0) -> str:
        """将大纲格式化为提示词文本"""
        lines = []
        for node in outline:
            prefix = "  " * indent
            label = node.get("label", "无标题")
            lines.append(f"{prefix}- {label}")

            if node.get("children"):
                lines.append(self._format_outline_for_prompt(node["children"], indent + 1))

        return "\n".join(lines)


# 全局服务实例
document_generator_service = DocumentGeneratorService()
