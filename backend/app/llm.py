"""Model client. All model calls go through here so the provider can be swapped."""

import json

from openai import OpenAI

from .config import Settings, get_settings


def get_client(provider: str = "meta", settings: Settings | None = None) -> tuple[OpenAI, str]:
    """Return an OpenAI-compatible client and the model id for a provider ("meta" or "baseten")."""
    settings = settings or get_settings(provider)
    # Retries cover transient 429/5xx errors; the timeout stops a stuck call from hanging an investigation.
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key, max_retries=3, timeout=180)
    return client, settings.model


def json_instruction(schema: dict) -> str:
    """Prompt suffix asking for JSON matching a schema.

    Used with Muse Spark Open on Baseten instead of constrained decoding (response_format),
    which there tends to pad the JSON with thousands of whitespace tokens.
    """
    return (
        "Reply with only a compact JSON object (no markdown, no extra text) matching this JSON Schema:\n"
        + json.dumps(schema)
    )


def extract_json(text: str, schema: dict) -> dict:
    """Parse the JSON object in a model reply and check the schema's required keys and enums."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in reply")
    obj = json.loads(text[start : end + 1])
    missing = set(schema.get("required", [])) - obj.keys()
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    for key, spec in schema.get("properties", {}).items():
        if "enum" in spec and key in obj and obj[key] not in spec["enum"]:
            raise ValueError(f"{key} must be one of {spec['enum']}")
    return obj
