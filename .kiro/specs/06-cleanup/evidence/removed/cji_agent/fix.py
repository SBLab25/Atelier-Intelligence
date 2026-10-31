import re

with open('tests/test_collector_models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace function definition
content = re.sub(
    r'(?s)def valid_event_data\(\) -> dict:\n\s+"""Factory.*?\n    }',
    '# \u2500\u2500 Fixtures (Shared fixtures now in conftest.py)',
    content
)

# Modify all test_ signatures to accept valid_event_data_dict
content = re.sub(r'(?m)^def test_([a-zA-Z0-9_]+)\(\):', r'def test_\1(valid_event_data_dict):', content)

# Replace valid_event_data() with valid_event_data_dict.copy()
content = content.replace('valid_event_data()', 'valid_event_data_dict.copy()')

with open('tests/test_collector_models.py', 'w', encoding='utf-8') as f:
    f.write(content)
