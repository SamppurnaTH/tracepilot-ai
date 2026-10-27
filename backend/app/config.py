import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model_api_key: str
    meta_base_url: str
    meta_model: str


def get_settings() -> Settings:
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set. Copy .env.example to .env and add your key.")
    return Settings(
        model_api_key=key,
        meta_base_url=os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"),
        meta_model=os.environ.get("META_MODEL", "muse-spark-1.3"),
    )
