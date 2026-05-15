import sys
sys.path.insert(0, 'backend')

from app.services.agent_engine.graph import _parse_decision_payload


def test_parse_valid_json():
    result = _parse_decision_payload('{"thought":"先检索","action":"tool","tool_name":"t_direct_search","tool_input":{"query":"测试"},"answer":null}')
    assert result['action'] == 'tool'
    assert result['tool_name'] == 't_direct_search'
    assert result['tool_input']['query'] == '测试'


def test_parse_markdown_json():
    result = _parse_decision_payload('```json\n{"thought":"完成","action":"final","tool_name":null,"tool_input":{},"answer":"最终答案"}\n```')
    assert result['action'] == 'final'
    assert result['answer'] == '最终答案'


def test_parse_plain_text_fallback():
    result = _parse_decision_payload('普通文本答案')
    assert result['action'] == 'final'
    assert result['answer'] == '普通文本答案'
