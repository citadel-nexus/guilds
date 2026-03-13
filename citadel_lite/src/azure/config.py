# src/azure/config.py
"""
Azure configuration loader.
Reads from environment variables. Returns AzureConfig with connection details.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AzureConfig:
    """Azure service connection configuration."""
    service_bus_connection: Optional[str] = None
    service_bus_queue: str = "citadel-events"
    cosmos_connection: Optional[str] = None
    cosmos_database: str = "citadel-lite"
    cosmos_container: str = "incidents"
    openai_endpoint: Optional[str] = None
    openai_key: Optional[str] = None
    openai_deployment: str = "gpt-4o"
    foundry_endpoint: Optional[str] = None
    foundry_key: Optional[str] = None
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    app_insights_connection: Optional[str] = None
    storage_connection: Optional[str] = None

    @property
    def foundry_project_endpoint(self) -> Optional[str]:
        """Return Foundry project endpoint, falling back to openai_endpoint."""
        return self.foundry_endpoint or self.openai_endpoint


def load_azure_config() -> AzureConfig:
    """Load Azure config from environment variables."""
    return AzureConfig(
        service_bus_connection=os.environ.get("AZURE_SERVICEBUS_CONNECTION"),
        service_bus_queue=os.environ.get("AZURE_SERVICEBUS_QUEUE", "citadel-events"),
        cosmos_connection=os.environ.get("AZURE_COSMOS_CONNECTION"),
        cosmos_database=os.environ.get("AZURE_COSMOS_DATABASE", "citadel-lite"),
        cosmos_container=os.environ.get("AZURE_COSMOS_CONTAINER", "incidents"),
        openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        openai_key=os.environ.get("AZURE_OPENAI_KEY"),
        openai_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        foundry_endpoint=os.environ.get("AZURE_FOUNDRY_ENDPOINT"),
        foundry_key=os.environ.get("AZURE_FOUNDRY_KEY"),
        subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID"),
        resource_group=os.environ.get("AZURE_RESOURCE_GROUP"),
        app_insights_connection=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
        storage_connection=os.environ.get("AZURE_STORAGE_CONNECTION"),
    )


def is_azure_enabled() -> bool:
    """Check if any Azure services are configured."""
    config = load_azure_config()
    return any([
        config.service_bus_connection,
        config.cosmos_connection,
        config.openai_endpoint,
        config.foundry_endpoint,
        config.app_insights_connection,
    ])
