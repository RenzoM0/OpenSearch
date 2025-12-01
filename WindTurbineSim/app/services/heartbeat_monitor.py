from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app.domain.messages import TurbineMessage, HeartbeatMessage, MessageType
from app.domain.stream_models import ConnectivityStatus


@dataclass
class HeartbeatMonitor:
    """
    Tracks expected heartbeats and determines connectivity status.

    Matches UML HeartbeatMonitor:
    - expectedIntervalSeconds
    - maxMissingCount
    - lastHeartbeatReceivedAt
    - missedHeartbeatsCount
    - connectivityStatus
    - lastStatusChangeAt
    - warningThresholdSeconds
    """

    expected_interval_seconds: int = 600          # how often a heartbeat is expected
    max_missing_count: int = 2                    # after this many missed -> OFFLINE
    warning_threshold_seconds: int = 0            # when to mark DEGRADED

    last_heartbeat_received_at: Optional[datetime] = None
    missed_heartbeats_count: int = 0

    connectivity_status: ConnectivityStatus = ConnectivityStatus.ONLINE
    last_status_change_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        # If no explicit warning threshold was set, default to 1.5x expected interval
        if self.warning_threshold_seconds <= 0:
            self.warning_threshold_seconds = int(self.expected_interval_seconds * 1.5)

    # --------------------------------------------------------------------- #
    # Lifecycle / state management
    # --------------------------------------------------------------------- #
    def mark_online(self) -> None:
        """Set status to ONLINE and reset missed heartbeat count."""
        if self.connectivity_status is not ConnectivityStatus.ONLINE:
            self.connectivity_status = ConnectivityStatus.ONLINE
            self.last_status_change_at = datetime.utcnow()
        self.missed_heartbeats_count = 0

    def mark_offline(self) -> None:
        """Set status to OFFLINE."""
        if self.connectivity_status is not ConnectivityStatus.OFFLINE:
            self.connectivity_status = ConnectivityStatus.OFFLINE
            self.last_status_change_at = datetime.utcnow()

    def mark_degraded(self) -> None:
        """Set status to DEGRADED."""
        if self.connectivity_status is not ConnectivityStatus.DEGRADED:
            self.connectivity_status = ConnectivityStatus.DEGRADED
            self.last_status_change_at = datetime.utcnow()

    def reset(self) -> None:
        """Reset monitor to initial state."""
        self.last_heartbeat_received_at = None
        self.missed_heartbeats_count = 0
        self.connectivity_status = ConnectivityStatus.ONLINE
        self.last_status_change_at = datetime.utcnow()

    # --------------------------------------------------------------------- #
    # Main behaviour
    # --------------------------------------------------------------------- #
    def register_message(self, message: TurbineMessage) -> None:
        """
        Register an incoming message.

        If it's a HeartbeatMessage, update last_heartbeat_received_at and
        reset the missed count.
        """
        if message.message_type is not MessageType.HEARTBEAT:
            return

        # It's a heartbeat
        self.last_heartbeat_received_at = message.timestamp
        self.missed_heartbeats_count = 0

        # On receiving a heartbeat we can move back towards ONLINE
        self.mark_online()

    def check_status(self, current_time: Optional[datetime] = None) -> ConnectivityStatus:
        """
        Evaluate connectivity status based on time since last heartbeat.

        - If no heartbeat has ever been seen -> keep current status.
        - If time since last heartbeat < warning threshold -> ONLINE.
        - If between warning threshold and max_missing_count * expected_interval
          -> DEGRADED.
        - If beyond that -> OFFLINE.
        """
        now = current_time or datetime.utcnow()

        if self.last_heartbeat_received_at is None:
            # No heartbeat received yet; keep whatever status we have.
            return self.connectivity_status

        elapsed = (now - self.last_heartbeat_received_at).total_seconds()

        # Determine how many expected heartbeats we have missed
        if self.expected_interval_seconds > 0:
            missing_estimate = int(elapsed // self.expected_interval_seconds)
        else:
            missing_estimate = 0

        self.missed_heartbeats_count = max(self.missed_heartbeats_count, missing_estimate)

        # Decide status based on thresholds
        if elapsed < self.warning_threshold_seconds:
            # Heartbeats are on time -> ONLINE
            self.mark_online()
        else:
            # Heartbeats are late
            if self.missed_heartbeats_count >= self.max_missing_count:
                self.mark_offline()
            else:
                self.mark_degraded()

        return self.connectivity_status
