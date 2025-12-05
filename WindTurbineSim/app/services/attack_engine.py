from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import random

from app.domain.attacks import (
    AttackProfile,
    ManipulationType,
    DurationMode,
)
from app.domain.messages import (
    TurbineMessage,
    TelemetryReading,
    MessageType,
)


@dataclass
class AttackEngine:
    """
    Applies attack profiles to outgoing messages.

    Key methods used by StreamingService:

    - start_attack(profile, messages_to_affect, end_time)
    - is_attack_active(now)
    - should_suppress(message, now) -> bool
    - apply_attack(message) -> TurbineMessage

    For the 'Loss of Contact' attack (MESSAGE_SUPPRESSION + TIME_WINDOW),
    we simply drop messages (usually heartbeats) while the attack is active.
    """

    enabled: bool = True

    active: bool = False
    active_profile: Optional[AttackProfile] = None

    remaining_messages_to_affect: Optional[int] = None
    suppression_end_time: Optional[datetime] = None

    last_applied_at: Optional[datetime] = None

    # Internal counter (for engine-level stats / debugging)
    affected_messages_count: int = 0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """Reset all attack state."""
        self.active = False
        self.active_profile = None
        self.remaining_messages_to_affect = None
        self.suppression_end_time = None
        self.last_applied_at = None
        self.affected_messages_count = 0

    def start_attack(
        self,
        profile: AttackProfile,
        messages_to_affect: Optional[int] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """
        Activate an attack with the given profile.

        StreamingService is responsible for computing `end_time` when
        using TIME_WINDOW attacks (like Loss of Contact).
        """
        if not self.enabled:
            return

        self.active_profile = profile
        self.active = True
        self.last_applied_at = None

        # Reset counters
        self.remaining_messages_to_affect = None
        self.suppression_end_time = None
        self.affected_messages_count = 0

        # Duration by message count
        if profile.duration_mode is DurationMode.SINGLE_MESSAGE:
            self.remaining_messages_to_affect = messages_to_affect or 1

        elif profile.duration_mode is DurationMode.MULTIPLE_MESSAGES:
            self.remaining_messages_to_affect = (
                messages_to_affect or profile.get_default_messages_to_affect()
            )

        # Duration by time window
        elif profile.duration_mode is DurationMode.TIME_WINDOW:
            if end_time is not None:
                self.suppression_end_time = end_time
            else:
                seconds = profile.get_default_duration_seconds()
                if seconds > 0:
                    self.suppression_end_time = datetime.utcnow() + timedelta(
                        seconds=seconds
                    )

    def stop_attack(self) -> None:
        """Deactivate any active attack and clear state."""
        self.active = False
        self.active_profile = None
        self.remaining_messages_to_affect = None
        self.suppression_end_time = None
        self.last_applied_at = None
        self.affected_messages_count = 0

    # ------------------------------------------------------------------ #
    # State checks
    # ------------------------------------------------------------------ #
    def _decrement_remaining(self) -> None:
        """Decrease remaining message budget and auto-stop if it reaches 0."""
        if self.remaining_messages_to_affect is None:
            return

        self.remaining_messages_to_affect -= 1
        if self.remaining_messages_to_affect <= 0:
            self.stop_attack()

    def is_attack_active(self, now: Optional[datetime] = None) -> bool:
        """
        Return True if an attack is currently active.

        Also performs auto-stop when the time window / message budget
        has been exhausted.
        """
        if not self.enabled:
            return False
        if not self.active:
            return False
        if self.active_profile is None:
            return False

        profile = self.active_profile
        now = now or datetime.utcnow()

        # TIME_WINDOW: stop after suppression_end_time
        if profile.duration_mode is DurationMode.TIME_WINDOW:
            if (
                self.suppression_end_time is not None
                and now >= self.suppression_end_time
            ):
                self.stop_attack()
                return False
            return True

        # MULTIPLE_MESSAGES / SINGLE_MESSAGE: stop when budget exhausted
        if (
            self.remaining_messages_to_affect is not None
            and self.remaining_messages_to_affect <= 0
        ):
            self.stop_attack()
            return False

        return True

    # ------------------------------------------------------------------ #
    # Decision points used by StreamingService
    # ------------------------------------------------------------------ #
    def should_suppress(self, message: TurbineMessage, now: datetime) -> bool:
        """
        Decide whether this message should be suppressed entirely.

        For 'Loss of Contact' (MESSAGE_SUPPRESSION + TIME_WINDOW) we drop
        messages instead of sending them into OpenSearch.

        Which messages are dropped is determined by the AttackProfile.
        For example:
        - for LOSS_CONTACT_10MIN (fields_affected: 'heartbeats (suppressed)')
          we only suppress heartbeat messages.
        """
        if not self.is_attack_active(now):
            return False

        profile = self.active_profile
        if profile is None or not profile.is_message_suppression():
            return False

        fields = (profile.fields_affected or "").lower()

        # Suppress heartbeats if profile mentions heartbeats
        if "heartbeat" in fields:
            if getattr(message, "message_type", None) is MessageType.HEARTBEAT:
                self._consume_one()
                return True

        # Suppress telemetry if profile mentions it explicitly or uses a generic marker
        if "telemetry" in fields or "all" in fields or fields.strip() == "":
            if getattr(message, "message_type", None) is MessageType.TELEMETRY:
                self._consume_one()
                return True

        return False

    def apply_attack(self, message: TurbineMessage) -> TurbineMessage:
        """
        Apply a data manipulation attack to the message (if any).

        For Loss of Contact (MESSAGE_SUPPRESSION attack), this method will not
        be used, because messages are already dropped by should_suppress().

        For DATA_MANIPULATION attacks (POWER_SPOOF, POWER_DRIFT, ...), this
        updates TelemetryReading values and marks them as attacked.
        """
        if not self.enabled:
            return message
        if not self.active:
            return message
        if self.active_profile is None:
            return message

        profile = self.active_profile
        if not profile.is_data_manipulation():
            return message

        # We only manipulate telemetry readings
        if not isinstance(message, TelemetryReading):
            return message

        manip_type = profile.manipulation_type

        if manip_type is ManipulationType.OVERRIDE:
            # Example: set power to an unrealistically high fixed value
            # (keep at least current value * 3 or 3000 kW)
            base = message.lv_active_power_kw or 0.0
            message.lv_active_power_kw = max(base * 3.0, 3000.0)

        elif manip_type is ManipulationType.MULTIPLY:
            # Example: double the active power
            message.lv_active_power_kw *= 2.0

        elif manip_type is ManipulationType.OFFSET:
            # Example: add a fixed offset to active power
            message.lv_active_power_kw += 500.0

        elif manip_type is ManipulationType.RANDOM_SPIKE:
            # Example: multiply by a random factor between 1.5 and 3.0
            factor = random.uniform(1.5, 3.0)
            message.lv_active_power_kw *= factor

        # Basic anomaly score bump to make it stand out
        current_score = message.anomaly_score or 0.0
        message.anomaly_score = max(current_score, 1.0)

        # Mark message as attacked using the profile id
        message.mark_attacked(
            notes=f"Attack profile {profile.attack_profile_id} applied"
        )

        # Refresh content description
        message.update_content()

        # Update engine bookkeeping
        self.last_applied_at = datetime.utcnow()
        self._decrement_remaining()
        self.affected_messages_count += 1

        return message

    # ------------------------------------------------------------------ #
    # Helpers / status
    # ------------------------------------------------------------------ #
    def _consume_one(self) -> None:
        """Update counters when we suppress one message."""
        self.affected_messages_count += 1
        self._decrement_remaining()

    def get_status_summary(self) -> str:
        """Return a short summary of the current attack state."""
        if not self.active or self.active_profile is None:
            return "No active attack"

        profile = self.active_profile
        remaining = (
            str(self.remaining_messages_to_affect)
            if self.remaining_messages_to_affect is not None
            else "N/A"
        )

        end_time = (
            self.suppression_end_time.isoformat()
            if self.suppression_end_time is not None
            else "N/A"
        )

        return (
            f"Active attack: {profile.name} "
            f"(category={profile.attack_category.name}, "
            f"mode={profile.duration_mode.name}, "
            f"remaining={remaining}, end_time={end_time})"
        )
