"""
Agent RAG Engine - 状态定义
定义 AgentState，用于 LangGraph 状态管理
"""
from typing import Annotated, Sequence, TypedDict, Optional, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def add_steps(left: List[dict], right: List[dict]) -> List[dict]:
    """
    Reducer 函数：将新的步骤追加到步骤列表
    """
    if not right:
        return left
    if not left:
        return right
    return left + right


def add_sources(left: Optional[List[dict]], right: Optional[List[dict]]) -> List[dict]:
    """
    Reducer 函数：将新的 sources 追加到列表
    """
    result = list(left or [])
    seen_ids = {item.get("id") for item in result if item.get("id")}

    if not right:
        return result

    for item in right:
        item_id = item.get("id")
        if item_id and item_id not in seen_ids:
            result.append(item)
            seen_ids.add(item_id)
        elif not item_id:
            result.append(item)
    return result


class AgentState(TypedDict):
    """
    Agent 状态定义
    
    使用 add_messages reducer 自动将新消息追加到列表末尾，而不是覆盖
    """
    # 核心字段：消息列表，使用 add_messages reducer 自动追加
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # 扩展字段：用于传递上下文信息
    user_id: Optional[int]  # 当前用户ID，用于隔离检索范围
    original_question: Optional[str]  # 用户当前轮的原始问题，避免 Agent 改写把检索带偏
    document_ids: Optional[List[str]]  # 限制搜索范围的文档ID列表
    task_id: Optional[str]  # 任务ID（用于任务停止检查）
    max_search_count: Optional[int]  # 最大检索次数（用户设置的迭代次数）
    search_count: Optional[int]  # 当前已执行的检索次数
    
    # 思考步骤列表，使用 add_steps reducer 自动追加
    steps: Annotated[List[dict], add_steps]  # Agent 思考步骤
    
    # 检索到的文档块列表，使用 add_sources reducer 自动追加并去重
    sources: Annotated[Optional[List[dict]], add_sources]  # 检索到的文档块

    # Agent 层自己解析出的下一步动作，不依赖模型原生 tool_calls
    pending_tool_name: Optional[str]
    pending_tool_input: Optional[dict]
    final_answer: Optional[str]
