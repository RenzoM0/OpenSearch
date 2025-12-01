from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class StreamMode(Enum):
    """How the turbine data is generated for streaming."""

    REPLAY_DATASET = auto()
    SYNTHETIC = auto()
    MIXED = auto()


class StreamStatus(Enum):
    """High-level lifecycle state of the streaming process."""

    IDLE = auto()
    RUNNING = auto()
    STOPPED = auto()
    ERROR = auto()


class ConnectivityStatus(Enum):
    """Connectivity state based on heartbeat monitoring."""

    ONLINE = auto()
    DEGRADED = auto()
    OFFLINE = auto()


@dataclass
class StreamConfig:
    """
    Configuration settings for streaming.

    Matches the UML StreamConfig:
    - enabled
    - dataIntervalSeconds
    - heartbeatIntervalSeconds
    - mode
    - targetIndex
    - batchSize
    - maxQueueSize
    - defaultAttackProfileId
    - lastUpdatedAt
    """

    enabled: bool = False

    data_interval_seconds: int = 600  # default: telemetry every 10 min
    heartbeat_interval_seconds: int = 60  # default: heartbeat every minute

    mode: StreamMode = StreamMode.REPLAY_DATASET
    target_index: str = "windturbine_live"

    batch_size: int = 1
    max_queue_size: int = 1_000

    default_attack_profile_id: Optional[str] = None

    last_updated_at: datetime = field(default_factory=datetime.utcnow)

    def enable(self) -> None:
        """Turn streaming on."""
        self.enabled = True
        self.last_updated_at = datetime.utcnow()

    def disable(self) -> None:
        """Turn streaming off."""
        self.enabled = False
        self.last_updated_at = datetime.utcnow()

    def update_intervals(
        self,
        data_seconds: Optional[int] = None,
        heartbeat_seconds: Optional[int] = None,
    ) -> None:
        """Update telemetry and heartbeat intervals."""
        if data_seconds is not None:
            self.data_interval_seconds = data_seconds
        if heartbeat_seconds is not None:
            self.heartbeat_interval_seconds = heartbeat_seconds
        self.last_updated_at = datetime.utcnow()

    def set_target_index(self, index_name: str) -> None:
        """Change the default OpenSearch index for streaming."""
        self.target_index = index_name
        self.last_updated_at = datetime.utcnow()

    def validate(self) -> bool:
        """
        Basic validation of config values.

        Returns True if configuration looks valid.
        """
        if self.data_interval_seconds <= 0:
            return False
        if self.heartbeat_interval_seconds <= 0:
            return False
        if self.batch_size <= 0:
            return False
        if self.max_queue_size < self.batch_size:
            return False
        if not self.target_index:
            return False
        return True


@dataclass
class StreamState:
    """
    Runtime state of the streaming process.

    Intentionally kept as a data holder (no complex behaviour),
    so that StreamingService encapsulates the logic.
    """

    status: StreamStatus = StreamStatus.IDLE
    connectivity_status: ConnectivityStatus = ConnectivityStatus.ONLINE

    last_telemetry_sent_at: Optional[datetime] = None
    last_heartbeat_sent_at: Optional[datetime] = None

    next_telemetry_scheduled_at: Optional[datetime] = None
    next_heartbeat_scheduled_at: Optional[datetime] = None

    current_dataset_position: int = 0

    total_messages_sent: int = 0
    total_attacked_messages: int = 0

    last_error_message: Optional[str] = None

    started_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
