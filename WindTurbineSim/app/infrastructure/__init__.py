"""
Infrastructure package.

Provides technical components that connect the domain to the outside world:
- Telemetry sources (dataset / synthetic)
- Message queue
- OpenSearch client
"""

from .telemetry_source import TelemetrySource, TelemetrySourceType
from .queue import TurbineMessageQueue, QueueStrategy
from .opensearch_client import OpenSearchClient

__all__ = [
    # telemetry sources
    "TelemetrySource",
    "TelemetrySourceType",
    # queue
    "TurbineMessageQueue",
    "QueueStrategy",
    # opensearch
    "OpenSearchClient",
]
