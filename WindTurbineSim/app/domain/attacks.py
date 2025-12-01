from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional, List

from .messages import TurbineMessage


class AttackCategory(Enum):
    """High-level category of attack."""

    DATA_MANIPULATION = auto()
    MESSAGE_SUPPRESSION = auto()  # e.g. loss of contact / dropped heartbeats


class ManipulationType(Enum):
    """How data is manipulated for DATA_MANIPULATION attacks."""

    OVERRIDE = auto()        # Set to fixed value
    MULTIPLY = auto()        # Multiply by factor
    OFFSET = auto()          # Add/subtract a delta
    RANDOM_SPIKE = auto()    # Insert random spikes / noise


class DurationMode(Enum):
    """How long an attack lasts."""

    SINGLE_MESSAGE = auto()
    MULTIPLE_MESSAGES = auto()
    TIME_WINDOW = auto()


class AttackEventStatus(Enum):
    """Lifecycle status of a concrete attack event."""

    SCHEDULED = auto()
    ACTIVE = auto()
    COMPLETED = auto()
    CANCELLED = auto()


@dataclass
class AttackProfile:
    """
    Template describing how an attack behaves.

    This corresponds to AttackProfile in the UML:
    - attackProfileId
    - name
    - description
    - attackCategory
    - manipulationType
    - durationMode
    - defaultMessagesToAffect
    - defaultDurationSeconds
    - fieldsAffected
    - severity
    - enabled
    """

    attack_profile_id: str
    name: str
    description: str

    attack_category: AttackCategory
    manipulation_type: Optional[ManipulationType] = None
    duration_mode: DurationMode = DurationMode.SINGLE_MESSAGE

    default_messages_to_affect: int = 1
    default_duration_seconds: int = 0  # 0 = not time-based

    fields_affected: str = ""  # e.g. "lv_active_power_kw, content"
    severity: int = 1  # 1..5

    enabled: bool = True

    def is_data_manipulation(self) -> bool:
        return self.attack_category is AttackCategory.DATA_MANIPULATION

    def is_message_suppression(self) -> bool:
        return self.attack_category is AttackCategory.MESSAGE_SUPPRESSION

    def get_default_messages_to_affect(self) -> int:
        return max(0, self.default_messages_to_affect)

    def get_default_duration_seconds(self) -> int:
        return max(0, self.default_duration_seconds)

    def get_summary(self) -> str:
        cat = self.attack_category.name
        manip = self.manipulation_type.name if self.manipulation_type else "N/A"
        return (
            f"{self.name} ({cat}, manipulation={manip}, "
            f"severity={self.severity}, fields={self.fields_affected})"
        )


@dataclass
class AttackEvent:
    """
    Concrete instance of an attack being executed.

    Matches the UML AttackEvent:
    - attackEventId
    - profile
    - status
    - triggeredBy
    - startTime
    - endTime
    - affectedMessagesCount
    - createdAt
    - notes
    """

    attack_event_id: str
    profile: AttackProfile
    triggered_by: str = "user"

    status: AttackEventStatus = AttackEventStatus.SCHEDULED

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    affected_messages_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""

    # Optional: keep direct references to affected messages
    affected_messages: List[TurbineMessage] = field(default_factory=list)

    def mark_started(self, start: Optional[datetime] = None) -> None:
        """Mark the attack as started."""
        self.status = AttackEventStatus.ACTIVE
        self.start_time = start or datetime.utcnow()

    def mark_completed(self, end: Optional[datetime] = None) -> None:
        """Mark the attack as completed."""
        self.status = AttackEventStatus.COMPLETED
        self.end_time = end or datetime.utcnow()

    def cancel(self, reason: str = "") -> None:
        """Cancel the attack and optionally record a reason."""
        self.status = AttackEventStatus.CANCELLED
        if reason:
            if self.notes:
                self.notes += f" | Cancelled: {reason}"
            else:
                self.notes = f"Cancelled: {reason}"

    def increment_affected_messages(self, message: Optional[TurbineMessage] = None) -> None:
        """
        Increment the count of affected messages and optionally register
        the message itself.
        """
        self.affected_messages_count += 1
        if message is not None:
            self.affected_messages.append(message)

    def is_active(self, now: Optional[datetime] = None) -> bool:
        """Return True if this event is currently active."""

        if self.status is not AttackEventStatus.ACTIVE:
            return False

        # If the profile uses a time window and we have an end_time, we can
        # use that to determine activity.
        if self.profile.duration_mode is DurationMode.TIME_WINDOW and self.end_time:
            current_time = now or datetime.utcnow()
            return self.start_time is not None and self.start_time <= current_time <= self.end_time

        # For other duration modes, the StreamingService / AttackEngine will
        # typically handle when to stop the attack; here we just check status.
        return True

    def compute_default_end_time(self) -> Optional[datetime]:
        """
        Compute an end time based on the profile's default duration, if any.

        Useful when scheduling TIME_WINDOW attacks.
        """
        if self.profile.duration_mode is not DurationMode.TIME_WINDOW:
            return None
        if self.profile.default_duration_seconds <= 0:
            return None
        if self.start_time is None:
            return None

        return self.start_time + timedelta(seconds=self.profile.default_duration_seconds)

    def get_summary(self) -> str:
        status = self.status.name
        profile_name = self.profile.name
        return (
            f"AttackEvent {self.attack_event_id}: {profile_name} "
            f"({status}, affected={self.affected_messages_count})"
        )
