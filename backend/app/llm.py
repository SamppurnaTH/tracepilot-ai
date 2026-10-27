"""Model client. All model calls go through here so the provider can be swapped later."""

from openai import OpenAI

from .config import Settings, get_settings


def get_client(settings: Settings | None = None) -> tuple[OpenAI, str]:
    """Return an OpenAI-compatible client for the Meta Model API and the model id to use."""
    settings = settings or get_settings()
    client = OpenAI(base_url=settings.meta_base_url, api_key=settings.model_api_key)
    return client, settings.meta_model
