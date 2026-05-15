from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, List, Dict, Optional
import uvicorn

app = FastAPI()

class ChatReq(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    chat_template_kwargs: Optional[dict] = None

@app.get('/v1/models')
def models():
    return {"object":"list","data":[{"id":"mock-agent-model","object":"model"}]}

@app.post('/v1/chat/completions')
def completions(req: ChatReq):
    msgs = req.messages or []
    last_user = ''
    tool_observations = []
    for m in msgs:
        content = m.get('content','')
        if m.get('role') == 'user':
            last_user = content
        if isinstance(content, str) and content.startswith('[Tool:'):
            tool_observations.append(content)

    # decision stage with context-meta prompt
    if last_user.startswith('上下文摘要(JSON)：'):
        if tool_observations:
            content = '{"thought":"已有工具结果，输出最终答案。","action":"final","tool_name":null,"tool_input":{},"answer":"基于检索结果，军事设施保护相关问题可先从主管机关职责、审批流程和法律责任三个方面概括回答。"}'
        else:
            content = '{"thought":"问题需要先检索知识库。","action":"tool","tool_name":"t_direct_search","tool_input":{"query":"军事设施保护主管机关职责 审批流程 法律责任"},"answer":null}'
    else:
        content = '{"thought":"默认直接回答。","action":"final","tool_name":null,"tool_input":{},"answer":"默认回答。"}'

    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 0,
        "model": req.model,
        "choices": [{"index":0,"message":{"role":"assistant","content":content},"finish_reason":"stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    }

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18001)
