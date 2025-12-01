from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from opensearchpy import OpenSearch, helpers

from app.domain.messages import (
    TurbineMessage,
    TelemetryReading,
    HeartbeatMessage,
    MessageType,
    MessageSource,
    HeartbeatStatus,
)


@dataclass
class OpenSearchClient:
    """
    Thin wrapper around the OpenSearch Python client.

    Responsibilities:
    - Manage connection (host, port, auth)
    - Create index if needed
    - Index single / bulk TurbineMessage documents
    - Query recent documents
    - Delete documents in a time range
    """

    host: str = "localhost"
    port: int = 9200
    scheme: str = "https"  # "http" or "https"

    username: Optional[str] = None
    password: Optional[str] = None

    default_index: str = "windturbine_live"
    request_timeout_seconds: int = 10

    connected: bool = field(default=False, init=False)
    last_error_message: Optional[str] = field(default=None, init=False)

    _client: OpenSearch = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialise the underlying OpenSearch client."""
        use_ssl = self.scheme == "https"

        http_auth = None
        if self.username and self.password:
            http_auth = (self.username, self.password)

        # 🔧 Dev-friendly settings for HTTPS with self-signed cert
        self._client = OpenSearch(
            hosts=[{"host": self.host, "port": self.port}],
            http_auth=http_auth,
            use_ssl=use_ssl,
            verify_certs=False,      # <– turn off strict cert checking
            ssl_show_warn=False,     # <– avoid noisy warnings in console
            timeout=self.request_timeout_seconds,
        )

    # -------------------------------------------------------------------------
    # Connection / health
    # -------------------------------------------------------------------------
    def ping(self) -> bool:
        """Check if OpenSearch is reachable."""
        try:
            ok = bool(self._client.ping())
            self.connected = ok
            if not ok:
                self.last_error_message = "Ping to OpenSearch failed."
            return ok
        except Exception as exc:  # noqa: BLE001
            self.connected = False
            self.last_error_message = f"Ping error: {exc}"
            return False

    def get_last_error(self) -> Optional[str]:
        """Return the last error message, if any."""
        return self.last_error_message

    # -------------------------------------------------------------------------
    # Index management
    # -------------------------------------------------------------------------
    def ensure_index_exists(self, index_name: Optional[str] = None) -> None:
        """
        Ensure that an index exists.

        For now we rely on dynamic mappings; if you want stricter control, you
        can add mappings/settings here later.
        """
        idx = index_name or self.default_index

        try:
            if not self._client.indices.exists(index=idx):
                self._client.indices.create(index=idx)
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"Error ensuring index '{idx}': {exc}"
            raise

    def set_default_index(self, index_name: str) -> None:
        """Update the default index used by this client."""
        self.default_index = index_name

    # -------------------------------------------------------------------------
    # Indexing
    # -------------------------------------------------------------------------
    def index_message(
        self,
        message: TurbineMessage,
        index_name: Optional[str] = None,
        refresh: bool = False,
    ) -> Optional[str]:
        """
        Index a single TurbineMessage into OpenSearch.

        Returns the document ID on success, or None on error.
        """
        idx = index_name or self.default_index
        body = message.to_document()

        try:
            response = self._client.index(index=idx, body=body, refresh=refresh)
            doc_id = response.get("_id")
            if doc_id:
                message.mark_sent(doc_id)
            return doc_id
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"Error indexing message: {exc}"
            return None

    def bulk_index_messages(
        self,
        messages: List[TurbineMessage],
        index_name: Optional[str] = None,
        refresh: bool = False,
    ) -> int:
        """
        Bulk index multiple messages.

        Returns the number of successfully indexed documents.
        """
        idx = index_name or self.default_index

        actions = []
        for msg in messages:
            body = msg.to_document()
            actions.append(
                {
                    "_index": idx,
                    "_source": body,
                }
            )

        try:
            success, _ = helpers.bulk(self._client, actions, refresh=refresh)
            # We don't get individual IDs here; if needed, we could switch to
            # explicit IDs or handle responses manually.
            return success
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"Error during bulk index: {exc}"
            return 0

    # -------------------------------------------------------------------------
    # Querying / search
    # -------------------------------------------------------------------------
    def search_recent_documents(
        self,
        index_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the most recent documents as generic dicts.

        This is useful to display a raw log in the UI.
        """
        idx = index_name or self.default_index

        query = {
            "size": limit,
            "sort": [{"timestamp": {"order": "desc"}}],
            "query": {"match_all": {}},
        }

        try:
            response = self._client.search(index=idx, body=query)
            hits = response.get("hits", {}).get("hits", [])
            return [hit.get("_source", {}) for hit in hits]
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"Error searching recent documents: {exc}"
            return []

    # (Optional) If you later want to reconstruct domain objects instead of raw dicts,
    # you can add a method like `search_recent_messages()` that uses message_type
    # in _source to create TelemetryReading / HeartbeatMessage instances.

    # -------------------------------------------------------------------------
    # Deleting by time range
    # -------------------------------------------------------------------------
    def delete_by_time_range(
        self,
        index_name: Optional[str],
        from_time: datetime,
        to_time: datetime,
    ) -> int:
        """
        Delete documents in a given time range.

        Returns number of documents that OpenSearch reports as deleted.
        """
        idx = index_name or self.default_index

        body = {
            "query": {
                "range": {
                    "timestamp": {
                        "gte": from_time.isoformat(),
                        "lte": to_time.isoformat(),
                    }
                }
            }
        }

        try:
            response = self._client.delete_by_query(index=idx, body=body)
            deleted = int(response.get("deleted", 0))
            return deleted
        except Exception as exc:  # noqa: BLE001
            self.last_error_message = f"Error deleting by time range: {exc}"
            return 0
