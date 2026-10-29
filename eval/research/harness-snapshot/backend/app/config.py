import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# provider -> (key env var, base URL env var, default base URL, model env var, default model)
PROVIDERS = {
    "meta": ("MODEL_API_KEY", "META_BASE_URL", "https://api.meta.ai/v1", "META_MODEL", "muse-spark-1.3"),
    # Muse Spark Open (open weights) served by Baseten. Hackathon keys only work with this exact model id.
    "baseten": (
        "BASETEN_API_KEY",
        "BASETEN_BASE_URL",
        "https://inference.baseten.co/v1",
        "BASETEN_MODEL",
        "meta-models/muse-spark-open-1026",
    ),
}


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    base_url: str
    model: str


def get_settings(provider: str = "meta") -> Settings:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider '{provider}'; expected one of {sorted(PROVIDERS)}")
    key_var, url_var, default_url, model_var, default_model = PROVIDERS[provider]
    key = os.environ.get(key_var, "")
    if not key:
        raise RuntimeError(f"{key_var} is not set. Copy .env.example to .env and add your key.")
    return Settings(
        provider=provider,
        api_key=key,
        base_url=os.environ.get(url_var, default_url),
        model=os.environ.get(model_var, default_model),
    )
