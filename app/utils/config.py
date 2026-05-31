"""Central configuration loaded from environment / .env file.

All secrets come from the environment - nothing is hard-coded. Every key is
optional so the agent can run a full pipeline with no credentials at all.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (app/utils/config.py -> project/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Load .env if present (does not override real env vars).
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # LLM (optional) — OpenAI or Qwen (DashScope OpenAI-compatible mode)
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_base_url: str = ""                 # e.g. DashScope compatible endpoint for Qwen

    # Macro API (optional)
    fred_api_key: str = ""

    # News (RSS + optional NewsAPI)
    newsapi_key: str = ""
    newsapi_query: str = (
        'London office OR "commercial real estate" London OR "Canary Wharf" office'
    )
    news_rss_feeds: str = (
        "https://www.bing.com/news/search?q=london+office+market&format=rss"
    )

    # Behaviour
    prefer_sample_data: bool = False
    db_path: str = "cre_agent.db"
    staleness_days_cre: int = 120      # quarterly CRE sample staleness threshold
    staleness_days_macro: int = 45     # macro series should refresh more often
    log_file: str = "logs/cre_agent.log"

    @property
    def rss_feed_list(self) -> list[str]:
        return [u.strip() for u in self.news_rss_feeds.split(",") if u.strip()]

    @property
    def llm_api_key(self) -> str:
        return self.openai_api_key.strip()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def llm_model(self) -> str:
        return self.openai_model

    @property
    def llm_base_url_resolved(self) -> str | None:
        if self.llm_base_url.strip():
            return self.llm_base_url.strip()
        if self.llm_provider.lower() == "qwen":
            return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return None

    @property
    def newsapi_enabled(self) -> bool:
        return bool(self.newsapi_key.strip())

    @property
    def fred_enabled(self) -> bool:
        return bool(self.fred_api_key.strip())

    @property
    def log_file_path(self) -> Path:
        path = Path(self.log_file)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def db_uri(self) -> str:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return f"sqlite:///{path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
