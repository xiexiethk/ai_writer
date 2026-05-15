import sys
sys.path.insert(0, 'backend')
from app.services.agent_engine.graph import _parse_decision_payload

samples = [
    ('{"thought":"先检索","action":"tool","tool_name":"t_direct_search","tool_input":{"query":"测试"},"answer":null}', 'tool'),
    ('```json\n{"thought":"完成","action":"final","tool_name":null,"tool_input":{},"answer":"最终答案"}\n```', 'final'),
    ('普通文本答案', 'final'),
]

for idx, (sample, expected) in enumerate(samples, start=1):
    result = _parse_decision_payload(sample)
    assert result['action'] == expected, (idx, result)
    print(f'case_{idx}_ok', result)

print('ALL_OK')
