from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from app.domain.stream_models import (
    StreamConfig,
    StreamState,
    StreamStatus,
)
from app.domain.attacks import (
    AttackProfile,
    AttackEvent,
    AttackEventStatus,
    DurationMode,
)
from app.domain.messages import (
    HeartbeatMessage,
    MessageType,
    MessageSource,
)
from app.infrastructure.telemetry_source import TelemetrySource
from app.infrastructure.queue import TurbineMessageQueue
from app.infrastructure.opensearch_client import OpenSearchClient
from .heartbeat_monitor import HeartbeatMonitor
from .attack_engine import AttackEngine


@dataclass
class StreamingService:
    """
    Orchestrates streaming of turbine messages.

    Responsibilities:
    - Pull messages from TelemetrySource
    - Fill and drain TurbineMessageQueue
    - Generate heartbeat messages
    - Apply AttackEngine (manipulation / suppression)
    - Track connectivity via HeartbeatMonitor
    - Persist messages via OpenSearchClient
    - Maintain StreamState and AttackEvent history
    """

    config: StreamConfig
    state: StreamState

    telemetry_source: TelemetrySource
    queue: TurbineMessageQueue
    heartbeat_monitor: HeartbeatMonitor
    attack_engine: AttackEngine
    opensearch_client: OpenSearchClient

    attack_events: List[AttackEvent] = field(default_factory=list)

    # --------------------------------------------------------------------- #
    # Lifecycle
    # --------------------------------------------------------------------- #
    def start(self) -> None:
        """Start streaming according to the current configuration."""
        now = datetime.utcnow()

        self.config.enable()
        self.state.status = StreamStatus.RUNNING
        self.state.started_at = self.state.started_at or now
        self.state.updated_at = now

        # Reset heartbeat & connectivity tracking
        self.heartbeat_monitor.reset()

        # Initialise telemetry source if needed
        if not self.telemetry_source.initialized:
            self.telemetry_source.initialize()

    def stop(self) -> None:
        """Stop streaming."""
        now = datetime.utcnow()

        self.config.disable()
        self.state.status = StreamStatus.STOPPED
        self.state.updated_at = now

    # --------------------------------------------------------------------- #
    # Attack control
    # --------------------------------------------------------------------- #
    def trigger_attack(
        self,
        profile: AttackProfile,
        messages_to_affect: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        triggered_by: str = "user",
    ) -> AttackEvent:
        """
        Start an attack using the given profile and register an AttackEvent.

        Returns the created AttackEvent.
        """
        now = datetime.utcnow()

        # Determine end time for TIME_WINDOW attacks
        end_time: Optional[datetime] = None
        if profile.duration_mode is DurationMode.TIME_WINDOW:
            seconds = (
                duration_seconds
                if duration_seconds is not None
                else profile.get_default_duration_seconds()
            )
            if seconds > 0:
                end_time = now + timedelta(seconds=seconds)

        # Start the engine attack
        self.attack_engine.start_attack(
            profile=profile,
            messages_to_affect=messages_to_affect,
            end_time=end_time,
        )

        # Create and register the event
        event_id = self._generate_attack_event_id(profile.attack_profile_id)
        event = AttackEvent(
            attack_event_id=event_id,
            profile=profile,
            triggered_by=triggered_by,
        )
        event.mark_started(now)
        self.attack_events.append(event)

        return event

    def _generate_attack_event_id(self, prefix: str = "ATTACK") -> str:
        """Generate a simple attack event id; can be replaced with UUID later."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        return f"{prefix}-{timestamp}"

    def _get_active_attack_event(self) -> Optional[AttackEvent]:
        """Return the most recent active AttackEvent, if any."""
        for event in reversed(self.attack_events):
            if event.status is AttackEventStatus.ACTIVE:
                return event
        return None

    def _update_attack_event_status(self, now: datetime) -> None:
        """
        If there is an active AttackEvent but the engine reports
        no active attack anymore, mark the event as completed.
        """
        active_event = self._get_active_attack_event()
        if active_event is None:
            return

        if not self.attack_engine.is_attack_active(now):
            active_event.mark_completed(now)

    # --------------------------------------------------------------------- #
    # Main tick
    # --------------------------------------------------------------------- #
    def tick(self, current_time: Optional[datetime] = None) -> None:
        """
        Perform one streaming cycle.

        This method should be called periodically (e.g. from a background
        task or a scheduler) to:
        - send heartbeat if due
        - enqueue telemetry if due
        - dequeue & send next message
        - update connectivity & attack event status
        """
        now = current_time or datetime.utcnow()

        if not self.config.enabled:
            self.state.status = StreamStatus.IDLE
            self.state.updated_at = now
            return

        # Ensure initial state
        if self.state.started_at is None:
            self.state.started_at = now

        self.state.status = StreamStatus.RUNNING
        self.state.updated_at = now

        # Make sure source is initialised
        if not self.telemetry_source.initialized:
            self.telemetry_source.initialize()

        # 1) Heartbeat generation
        self._maybe_send_heartbeat(now)

        # 2) Enqueue telemetry if due
        self._maybe_enqueue_telemetry(now)

        # 3) Dequeue and process next message
        self._send_next_message(now)

        # 4) Update connectivity from heartbeat monitor
        self._update_connectivity(now)

        # 5) Update attack event based on engine state
        self._update_attack_event_status(now)

    # --------------------------------------------------------------------- #
    # Heartbeat logic
    # --------------------------------------------------------------------- #
    def _is_heartbeat_due(self, now: datetime) -> bool:
        """Return True if it is time to send a heartbeat."""
        if self.state.last_heartbeat_sent_at is None:
            return True

        elapsed = (now - self.state.last_heartbeat_sent_at).total_seconds()
        return elapsed >= self.config.heartbeat_interval_seconds

    def _maybe_send_heartbeat(self, now: datetime) -> None:
        """Generate and send a heartbeat message if due (and not suppressed)."""
        if not self._is_heartbeat_due(now):
            return

        if self.telemetry_source.turbine is None:
            # In practice you will configure a turbine before starting streaming.
            raise ValueError("TelemetrySource.turbine is not configured")

        # Create heartbeat message
        msg = HeartbeatMessage(
            message_id=self._generate_message_id("HB"),
            turbine=self.telemetry_source.turbine,
            timestamp=now,
            message_type=MessageType.HEARTBEAT,
            source=MessageSource.SIMULATION,
        )

        # Check if current attack wants to suppress this message
        if self.attack_engine.should_suppress(msg, now):
            # Suppressed -> do not index or register; from the system's point of
            # view, the heartbeat simply never arrived.
            return

        # Index heartbeat
        self.opensearch_client.index_message(msg, self.config.target_index)
        self.state.last_heartbeat_sent_at = now
        self.state.total_messages_sent += 1
        if msg.is_attacked:  # <-- fixed name
            self.state.total_attacked_messages += 1

        # Register with heartbeat monitor for connectivity tracking
        self.heartbeat_monitor.register_message(msg)

    # --------------------------------------------------------------------- #
    # Telemetry logic
    # --------------------------------------------------------------------- #
    def _is_telemetry_due(self, now: datetime) -> bool:
        """Return True if it is time to send telemetry."""
        if self.state.last_telemetry_sent_at is None:
            return True

        elapsed = (now - self.state.last_telemetry_sent_at).total_seconds()
        return elapsed >= self.config.data_interval_seconds

    def _maybe_enqueue_telemetry(self, now: datetime) -> None:
        """Ask the TelemetrySource for the next message and enqueue it, if due."""
        if not self._is_telemetry_due(now):
            return

        if not self.telemetry_source.has_more_messages():
            # No more data from this source (for finite/dataset replay)
            return

        msg = self.telemetry_source.get_next_message()
        if msg is None:
            return

        self.queue.enqueue(msg)

    def _send_next_message(self, now: datetime) -> None:
        """Dequeue the next message, apply attacks, and send to OpenSearch."""
        msg = self.queue.dequeue()
        if msg is None:
            return

        # Check suppression first (MESSAGE_SUPPRESSION attacks)
        if self.attack_engine.should_suppress(msg, now):
            # Message is suppressed and will not be sent
            return

        # Apply DATA_MANIPULATION attacks
        msg = self.attack_engine.apply_attack(msg)

        # Index message
        self.opensearch_client.index_message(msg, self.config.target_index)

        # Update generic counters
        self.state.total_messages_sent += 1
        if msg.is_attacked:  # <-- fixed name
            self.state.total_attacked_messages += 1

        # Update per-type state & heartbeat monitor
        if msg.message_type is MessageType.TELEMETRY:
            self.state.last_telemetry_sent_at = now
            # Track dataset position if applicable
            self.state.current_dataset_position = self.telemetry_source.current_position

        elif msg.message_type is MessageType.HEARTBEAT:
            self.state.last_heartbeat_sent_at = now
            # normally heartbeats won't come from source, but we keep it generic
            self.heartbeat_monitor.register_message(msg)

    # --------------------------------------------------------------------- #
    # Connectivity
    # --------------------------------------------------------------------- #
    def _update_connectivity(self, now: datetime) -> None:
        """Pull connectivity status from HeartbeatMonitor into StreamState."""
        status = self.heartbeat_monitor.check_status(now)
        self.state.connectivity_status = status

    # --------------------------------------------------------------------- #
    # Helpers / status
    # --------------------------------------------------------------------- #
    def _generate_message_id(self, prefix: str) -> str:
        """Generate a simple message id; can be replaced by UUID later."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        return f"{prefix}-{timestamp}"

    def get_status_summary(self) -> str:
        """Return a short summary of the current stream state for UI/logs."""
        return (
            f"Streaming status={self.state.status.name}, "
            f"connectivity={self.state.connectivity_status.name}, "
            f"total_messages={self.state.total_messages_sent}, "
            f"attacked_messages={self.state.total_attacked_messages}"
        )
