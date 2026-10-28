import pytest

from app.llm import extract_json

SCHEMA = {
    "type": "object",
    "properties": {"claim": {"type": "string"}, "confidence": {"type": "string", "enum": ["low", "medium", "high"]}},
    "required": ["claim", "confidence"],
}


@pytest.mark.parametrize(
    "text",
    [
        '{"claim": "x", "confidence": "high"}',
        'Here you go:\n```json\n{"claim": "x", "confidence": "high"}\n```',
        '{ \n  "claim": "x",\n  "confidence":                 "high"\n}',
    ],
)
def test_extract_json_accepts_wrapped_or_padded_json(text):
    assert extract_json(text, SCHEMA) == {"claim": "x", "confidence": "high"}


@pytest.mark.parametrize(
    "text, message",
    [
        ("no json here", "no JSON object"),
        ('{"claim": "x"}', "missing fields"),
        ('{"claim": "x", "confidence": "certain"}', "must be one of"),
    ],
)
def test_extract_json_rejects_bad_replies(text, message):
    with pytest.raises(ValueError, match=message):
        extract_json(text, SCHEMA)
