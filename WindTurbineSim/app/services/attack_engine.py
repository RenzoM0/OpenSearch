from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import random

from app.domain.attacks import (
    AttackProfile,
    AttackCategory,
    ManipulationType,
    DurationMode,
)
from app.domain.messages import TurbineMessage, TelemetryReading


@dataclass
class AttackEngine:
    """
    Applies AttackProfile rules to TurbineMessage instances.

    Supports two main categories:
    - DATA_MANIPULATION  -> modify message fields (e.g. spoof power values)
    - MESSAGE_SUPPRESSION -> decide to drop/suppress messages (loss of contact)
    """

    active: bool = field(default=False, init=False)
    active_profile: Optional[AttackProfile] = field(default=None, init=False)

    remaining_messages_to_affect: Optional[int] = field(default=None, init=False)
    suppression_end_time: Optional[datetime] = field(default=None, init=False)

    last_applied_at: Optional[datetime] = field(default=None, init=False)

    random_seed: Optional[int] = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.random_seed is not None:
            random.seed(self.random_seed)

    # --------------------------------------------------------------------- #
    # Lifecycle
    # --------------------------------------------------------------------- #
    def start_attack(
        self,
        profile: AttackProfile,
        messages_to_affect: Optional[int] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """
        Activate an attack with the given profile.

        - For SINGLE_MESSAGE: affects 1 (or messages_to_affect if provided)
        - For MULTIPLE_MESSAGES: affects profile.default_messages_to_affect
          (or messages_to_affect if provided)
        - For TIME_WINDOW: uses end_time, or computes it from
          profile.default_duration_seconds.
        """
        if not self.enabled:
            # Engine is globally disabled, do nothing.
            return

        self.active_profile = profile
        self.active = True
        self.last_applied_at = None

        # Reset counters
        self.remaining_messages_to_affect = None
        self.suppression_end_time = None

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

    def is_attack_active(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if an attack is currently active, considering:
        - engine enabled flag
        - active flag
        - remaining_messages_to_affect (if used)
        - suppression_end_time (for TIME_WINDOW)
        """
        if not self.enabled or not self.active or self.active_profile is None:
            return False

        # Check message count
        if (
            self.remaining_messages_to_affect is not None
            and self.remaining_messages_to_affect <= 0
        ):
            return False

        # Check time window
        if (
            self.active_profile.duration_mode is DurationMode.TIME_WINDOW
            and self.suppression_end_time is not None
        ):
            now = current_time or datetime.utcnow()
            if now > self.suppression_end_time:
                return False

        return True

    def reset(self) -> None:
        """Reset the engine completely."""
        self.stop_attack()
        # Note: enabled and random_seed are left as-is

    # --------------------------------------------------------------------- #
    # Application of attacks
    # --------------------------------------------------------------------- #
    def _decrement_remaining(self) -> None:
        if self.remaining_messages_to_affect is not None:
            self.remaining_messages_to_affect -= 1

    def apply_attack(self, message: TurbineMessage) -> TurbineMessage:
        """
        Apply a DATA_MANIPULATION attack to a message.

        - If no active attack, returns the message unchanged.
        - If the active profile is MESSAGE_SUPPRESSION, this method
          will NOT suppress the message; use should_suppress() for that.
        """
        if not self.is_attack_active():
            return message

        profile = self.active_profile
        assert profile is not None  # for type checkers

        # Only manipulate data for DATA_MANIPULATION attacks
        if not profile.is_data_manipulation():
            return message

        # Currently we only manipulate TelemetryReading objects
        if not isinstance(message, TelemetryReading):
            return message

        # Very simple manipulation logic; can be extended later:
        manip_type = profile.manipulation_type

        if manip_type is ManipulationType.OVERRIDE:
            # Example: set power to an unrealistically high fixed value
            message.lv_active_power_kw = max(
                message.lv_active_power_kw, message.lv_active_power_kw * 3.0 or 3000.0
            )

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
        message.anomaly_score = max(message.anomaly_score, 1.0)

        # Mark message as attacked
        message.mark_as_attack(profile.attack_profile_id)

        # Optionally refresh content description
        message.update_content()

        # Update engine bookkeeping
        self.last_applied_at = datetime.utcnow()
        self._decrement_remaining()

        return message

    def should_suppress(
        self,
        message: TurbineMessage,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        Decide whether a message should be suppressed (not sent).

        Only applies when:
        - attack is active
        - category is MESSAGE_SUPPRESSION (e.g. loss of contact)
        """
        if not self.is_attack_active(current_time):
            return False

        profile = self.active_profile
        assert profile is not None  # for type checkers

        if not profile.is_message_suppression():
            return False

        # If TIME_WINDOW-based, re-check time window here (defensive)
        if (
            profile.duration_mode is DurationMode.TIME_WINDOW
            and self.suppression_end_time is not None
        ):
            now = current_time or datetime.utcnow()
            if now > self.suppression_end_time:
                return False

        # At this point, we are in an active suppression window
        self.last_applied_at = datetime.utcnow()
        self._decrement_remaining()

        # We don't change the message here; StreamingService will simply not send it
        return True

    # --------------------------------------------------------------------- #
    # Introspection / UI helpers
    # --------------------------------------------------------------------- #
    def get_status_summary(self) -> str:
        """Return a short human-readable status summary for UI/logs."""
        if not self.enabled:
            return "Attack engine disabled"

        if not self.active or self.active_profile is None:
            return "No active attack"

        profile = self.active_profile
        cat = profile.attack_category.name
        mode = profile.duration_mode.name

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
            f"(category={cat}, mode={mode}, remaining={remaining}, "
            f"end_time={end_time})"
        )
