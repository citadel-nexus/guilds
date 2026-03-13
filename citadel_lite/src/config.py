# src/config.py
"""
Unified configuration loader for Citadel Lite.

Loads citadel.config.yaml from the project root. Environment variables
override YAML values. Every field has a sensible default — the pipeline
runs fully local with file-based backends when nothing is configured.

Usage:
    from src.config import get_config
    cfg = get_config()
    if cfg.github_token:
        ...
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

try:
    from dotenv import load_dotenv as _load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


@dataclass
class CitadelConfig:
    """Flat view of all configuration values."""

    # Pipeline
    execution_mode: str = "local"
    agent_version: str = "v2"
    sse_enabled: bool = True

    # LLM — Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"

    # LLM — OpenAI direct
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # GitLab
    gitlab_token: str = ""
    gitlab_url: str = ""

    # Dashboard
    dashboard_enabled: bool = True
    dashboard_poll_interval_ms: int = 2000

    # Notifications — Slack
    slack_webhook_url: str = ""
    slack_channel: str = "#citadel-alerts"

    # Notifications — Teams
    teams_webhook_url: str = ""

    # Notifications — Generic webhook
    notification_webhook_url: str = ""
    notification_webhook_headers: Dict[str, str] = field(default_factory=dict)

    # Azure — Service Bus
    azure_servicebus_connection: str = ""
    azure_servicebus_queue: str = "citadel-events"

    # Azure — Cosmos DB
    azure_cosmos_connection: str = ""
    azure_cosmos_database: str = "citadel-lite"
    azure_cosmos_container: str = "incidents"

    # Azure — Foundry
    azure_foundry_endpoint: str = ""
    azure_foundry_key: str = ""

    # Azure — App Insights
    azure_appinsights_connection: str = ""

    # Azure — Storage
    azure_storage_connection: str = ""

    # Azure — AI Search
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "citadel-incidents"

    # Memory
    memory_backend: str = "local"  # local | faiss | azure_search
    faiss_enabled: bool = False

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Notion
    notion_api_key: str = ""
    notion_database_id: str = ""

    # Slack (enhanced bot)
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # --- Derived checks ---

    @property
    def has_llm(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_key) or bool(self.openai_api_key)

    @property
    def has_github(self) -> bool:
        return bool(self.github_token)

    @property
    def has_azure(self) -> bool:
        return bool(
            self.azure_servicebus_connection
            or self.azure_cosmos_connection
            or self.azure_appinsights_connection
            or self.azure_foundry_endpoint
            or self.azure_search_endpoint
        )

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def has_notion(self) -> bool:
        return bool(self.notion_api_key and self.notion_database_id)

    @property
    def has_slack_bot(self) -> bool:
        return bool(self.slack_bot_token)

    @property
    def has_azure_search(self) -> bool:
        return bool(self.azure_search_endpoint and self.azure_search_key)

    @property
    def has_slack(self) -> bool:
        return bool(self.slack_webhook_url)

    @property
    def has_teams(self) -> bool:
        return bool(self.teams_webhook_url)

    @property
    def has_notifications(self) -> bool:
        return self.has_slack or self.has_teams or bool(self.notification_webhook_url)

    def summary(self) -> Dict[str, Any]:
        """Return a safe summary (no secrets) of what's configured."""
        return {
            "execution_mode": self.execution_mode,
            "agent_version": self.agent_version,
            "sse_enabled": self.sse_enabled,
            "dashboard_enabled": self.dashboard_enabled,
            "llm_configured": self.has_llm,
            "llm_backend": (
                "azure_openai" if (self.azure_openai_endpoint and self.azure_openai_key)
                else "openai" if self.openai_api_key
                else "none"
            ),
            "github_configured": self.has_github,
            "azure_configured": self.has_azure,
            "azure_services": [
                s for s, v in [
                    ("service_bus", self.azure_servicebus_connection),
                    ("cosmos", self.azure_cosmos_connection),
                    ("app_insights", self.azure_appinsights_connection),
                    ("foundry", self.azure_foundry_endpoint),
                    ("storage", self.azure_storage_connection),
                    ("ai_search", self.azure_search_endpoint),
                ] if v
            ],
            "notifications": [
                n for n, v in [
                    ("slack", self.slack_webhook_url),
                    ("teams", self.teams_webhook_url),
                    ("webhook", self.notification_webhook_url),
                ] if v
            ],
            "memory_backend": self.memory_backend,
            "faiss_enabled": self.faiss_enabled,
            "supabase_configured": self.has_supabase,
            "notion_configured": self.has_notion,
            "slack_bot_configured": self.has_slack_bot,
            "azure_search_configured": self.has_azure_search,
        }


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML config if file exists and pyyaml is available."""
    if not path.exists() or not _HAS_YAML:
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _get(data: Dict, *keys: str, default: Any = "") -> Any:
    """Nested dict lookup."""
    current = data
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k, default)
    return current if current is not None else default


def load_config(config_path: Optional[Path] = None) -> CitadelConfig:
    """
    Load configuration from YAML + environment variables.
    .env file is loaded first, then YAML, then env vars (env vars win).
    """
    # Load .env from project root (silently ignored if not found)
    if _HAS_DOTENV:
        _env_path = Path(__file__).resolve().parent.parent / ".env"
        _load_dotenv(_env_path, override=False)

    path = config_path or Path(__file__).resolve().parent.parent / "citadel.config.yaml"
    data = _load_yaml(path)

    def env_or_yaml(env_var: str, *yaml_keys: str, default: Any = "") -> str:
        """Env var wins, then YAML, then default."""
        return os.environ.get(env_var, "") or str(_get(data, *yaml_keys, default=default))

    return CitadelConfig(
        # Pipeline
        execution_mode=env_or_yaml("EXECUTION_MODE", "pipeline", "execution_mode", default="local"),
        agent_version=str(_get(data, "pipeline", "agent_version", default="v2")),
        sse_enabled=bool(_get(data, "pipeline", "sse_enabled", default=True)),

        # LLM — Azure OpenAI
        azure_openai_endpoint=env_or_yaml("AZURE_OPENAI_ENDPOINT", "llm", "azure_openai", "endpoint"),
        azure_openai_key=env_or_yaml("AZURE_OPENAI_KEY", "llm", "azure_openai", "api_key"),
        azure_openai_deployment=env_or_yaml("AZURE_OPENAI_DEPLOYMENT", "llm", "azure_openai", "deployment", default="gpt-4o"),

        # LLM — OpenAI
        openai_api_key=env_or_yaml("OPENAI_API_KEY", "llm", "openai", "api_key"),
        openai_model=env_or_yaml("OPENAI_MODEL", "llm", "openai", "model", default="gpt-4o"),

        # GitHub
        github_token=env_or_yaml("GITHUB_TOKEN", "github", "token"),
        github_webhook_secret=env_or_yaml("GITHUB_WEBHOOK_SECRET", "github", "webhook_secret"),

        # GitLab
        gitlab_token=env_or_yaml("GITLAB_TOKEN", "gitlab", "token"),
        gitlab_url=env_or_yaml("GITLAB_URL", "gitlab", "url"),

        # Dashboard
        dashboard_enabled=bool(_get(data, "dashboard", "enabled", default=True)),
        dashboard_poll_interval_ms=int(_get(data, "dashboard", "poll_interval_ms", default=2000)),

        # Notifications
        slack_webhook_url=env_or_yaml("SLACK_WEBHOOK_URL", "notifications", "slack", "webhook_url"),
        slack_channel=str(_get(data, "notifications", "slack", "channel", default="#citadel-alerts")),
        teams_webhook_url=env_or_yaml("TEAMS_WEBHOOK_URL", "notifications", "teams", "webhook_url"),
        notification_webhook_url=env_or_yaml("NOTIFICATION_WEBHOOK_URL", "notifications", "webhook", "url"),
        notification_webhook_headers=dict(_get(data, "notifications", "webhook", "headers", default={}) or {}),

        # Azure
        azure_servicebus_connection=env_or_yaml("AZURE_SERVICEBUS_CONNECTION", "azure", "service_bus", "connection_string"),
        azure_servicebus_queue=str(_get(data, "azure", "service_bus", "queue_name", default="citadel-events")),
        azure_cosmos_connection=env_or_yaml("AZURE_COSMOS_CONNECTION", "azure", "cosmos", "connection_string"),
        azure_cosmos_database=str(_get(data, "azure", "cosmos", "database", default="citadel-lite")),
        azure_cosmos_container=str(_get(data, "azure", "cosmos", "container", default="incidents")),
        azure_foundry_endpoint=env_or_yaml("AZURE_FOUNDRY_ENDPOINT", "azure", "foundry", "endpoint"),
        azure_foundry_key=env_or_yaml("AZURE_FOUNDRY_KEY", "azure", "foundry", "api_key"),
        azure_appinsights_connection=env_or_yaml("APPLICATIONINSIGHTS_CONNECTION_STRING", "azure", "app_insights", "connection_string"),
        azure_storage_connection=env_or_yaml("AZURE_STORAGE_CONNECTION", "azure", "storage", "connection_string"),

        # Azure — AI Search
        azure_search_endpoint=env_or_yaml("AZURE_SEARCH_ENDPOINT", "azure", "ai_search", "endpoint"),
        azure_search_key=env_or_yaml("AZURE_SEARCH_KEY", "azure", "ai_search", "api_key"),
        azure_search_index=str(_get(data, "azure", "ai_search", "index_name", default="citadel-incidents")),

        # Memory
        memory_backend=str(_get(data, "memory", "backend", default="local")),
        faiss_enabled=bool(_get(data, "memory", "faiss_enabled", default=False)),

        # Supabase
        supabase_url=env_or_yaml("SUPABASE_URL", "supabase", "url"),
        supabase_key=env_or_yaml("SUPABASE_KEY", "supabase", "api_key"),

        # Notion
        notion_api_key=env_or_yaml("NOTION_API_KEY", "notion", "api_key"),
        notion_database_id=str(_get(data, "notion", "database_id", default="")),

        # Slack (enhanced)
        slack_bot_token=env_or_yaml("SLACK_BOT_TOKEN", "slack", "bot_token"),
        slack_signing_secret=env_or_yaml("SLACK_SIGNING_SECRET", "slack", "signing_secret"),
    )


# Module-level singleton
_config: Optional[CitadelConfig] = None


def get_config() -> CitadelConfig:
    """Get the singleton config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
