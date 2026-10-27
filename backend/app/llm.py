"""Model client. All model calls go through here so the provider can be swapped."""

from openai import OpenAI

from .config import Settings, get_settings


def get_client(provider: str = "meta", settings: Settings | None = None) -> tuple[OpenAI, str]:
    """Return an OpenAI-compatible client and the model id for a provider ("meta" or "baseten")."""
    settings = settings or get_settings(provider)
    # Retries cover transient 429/5xx errors; the timeout stops a stuck call from hanging an investigation.
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key, max_retries=3, timeout=180)
    return client, settings.model
