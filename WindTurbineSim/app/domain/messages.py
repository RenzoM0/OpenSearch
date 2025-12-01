from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional

from app.domain.wind_turbine import WindTurbine


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MessageType(Enum):
    TELEMETRY = auto()
    HEARTBEAT = auto()
    ATTACK_LOG = auto()


class MessageSource(Enum):
    LIVE_STREAM = auto()
    SIMULATION = auto()
    REPLAY_DATASET = auto()
    SYNTHETIC = auto()


class HeartbeatStatus(Enum):
    OK = auto()
    WARNING = auto()
    ERROR = auto()


# ---------------------------------------------------------------------------
# Base message
# ---------------------------------------------------------------------------


@dataclass
class TurbineMessage:
    """
    Base message type for anything we send to OpenSearch.

    Subclasses (TelemetryReading, HeartbeatMessage, …) add extra fields but
    re-use the base indexing logic.
    """

    message_id: str
    turbine: WindTurbine
    timestamp: datetime
    message_type: MessageType
    source: MessageSource

    is_attacked: bool = False
    attack_notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    content: str = ""

    def mark_attacked(self, notes: str = "", **metadata: Any) -> None:
        self.is_attacked = True
        self.attack_notes = notes
        if metadata:
            self.extra.setdefault("attack_metadata", {}).update(metadata)

    def to_document_base(self) -> Dict[str, Any]:
        """
        Base fields shared by all message types for indexing into OpenSearch.

        IMPORTANT: timestamp is stored as '@timestamp' so dashboards and
        time-series visualisations can find it.
        """
        doc: Dict[str, Any] = {
            "@timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
            "turbine_id": self.turbine.turbine_id,
            "turbine_name": self.turbine.name,
            "message_type": self.message_type.name,
            "source": self.source.name,
            "is_attacked": self.is_attacked,
            "attack_notes": self.attack_notes,
            "content": self.content,
        }

        if self.extra:
            # Last write wins if keys overlap
            doc.update(self.extra)

        return doc

    def to_document(self) -> Dict[str, Any]:
        """
        Default document representation for OpenSearch.

        Subclasses normally call to_document_base() and then add fields.
        """
        return self.to_document_base()


# ---------------------------------------------------------------------------
# Telemetry messages
# ---------------------------------------------------------------------------


@dataclass
class TelemetryReading(TurbineMessage):
    wind_speed_ms: float = 0.0
    lv_active_power_kw: float = 0.0
    theoretical_power_curve_kwh: float = 0.0
    wind_direction_deg: Optional[float] = None
    anomaly_score: Optional[float] = None

    def update_content(self) -> None:
        """
        Regenerate the human-readable 'content' field for this reading.
        """
        self.content = (
            f"Turbine {self.turbine.name} at {self.timestamp.isoformat()} – "
            f"wind {self.wind_speed_ms:.2f} m/s, "
            f"active power {self.lv_active_power_kw:.2f} kW."
        )

    def to_document(self) -> Dict[str, Any]:
        doc = self.to_document_base()
        doc.update(
            wind_speed_ms=self.wind_speed_ms,
            lv_active_power_kw=self.lv_active_power_kw,
            theoretical_power_curve_kwh=self.theoretical_power_curve_kwh,
            wind_direction_deg=self.wind_direction_deg,
            anomaly_score=self.anomaly_score,
        )
        return doc


# ---------------------------------------------------------------------------
# Heartbeat messages
# ---------------------------------------------------------------------------


@dataclass
class HeartbeatMessage(TurbineMessage):
    status: HeartbeatStatus = HeartbeatStatus.OK
    interval_seconds: int = 0
    has_data_connection: bool = True

    def update_content(self) -> None:
        state = "OK" if self.has_data_connection else "NO DATA"
        self.content = (
            f"Heartbeat {self.status.name} – interval {self.interval_seconds}s, "
            f"data connection {state}."
        )

    def to_document(self) -> Dict[str, Any]:
        doc = self.to_document_base()
        doc.update(
            heartbeat_status=self.status.name,
            heartbeat_interval_seconds=self.interval_seconds,
            has_data_connection=self.has_data_connection,
        )
        return doc


__all__ = [
    "MessageType",
    "MessageSource",
    "HeartbeatStatus",
    "TurbineMessage",
    "TelemetryReading",
    "HeartbeatMessage",
]
