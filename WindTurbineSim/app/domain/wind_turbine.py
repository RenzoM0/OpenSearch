from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class TurbineStatus(Enum):
    """High-level status of a wind turbine."""

    UNKNOWN = auto()
    ONLINE = auto()
    OFFLINE = auto()
    ERROR = auto()


@dataclass
class WindTurbine:
    """
    Domain model representing a single wind turbine.

    This maps directly to the WindTurbine class in your UML:
    - turbineId
    - name
    - location
    - ratedPowerKw
    - description
    - status
    - createdAt
    - updatedAt
    """

    turbine_id: str
    name: str
    location: str
    rated_power_kw: float
    description: str = ""

    status: TurbineStatus = TurbineStatus.UNKNOWN
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def update_status(self, new_status: TurbineStatus) -> None:
        """Update the turbine's status."""
        self.status = new_status
        self.updated_at = datetime.utcnow()

    def update_details(
        self,
        name: Optional[str] = None,
        location: Optional[str] = None,
        rated_power_kw: Optional[float] = None,
        description: Optional[str] = None,
    ) -> None:
        """
        Update turbine metadata.

        Any argument left as None will not be changed.
        """
        if name is not None:
            self.name = name
        if location is not None:
            self.location = location
        if rated_power_kw is not None:
            self.rated_power_kw = rated_power_kw
        if description is not None:
            self.description = description

        self.updated_at = datetime.utcnow()

    def get_display_name(self) -> str:
        """Return a human-friendly name for UI use."""
        if self.location:
            return f"{self.name} (@{self.location})"
        return self.name

    def get_status_summary(self) -> str:
        """Return a short human-readable status summary."""
        status_text = self.status.name

        if self.status is TurbineStatus.ONLINE:
            detail = "sending data normally"
        elif self.status is TurbineStatus.OFFLINE:
            detail = "no data / lost contact"
        elif self.status is TurbineStatus.ERROR:
            detail = "error detected"
        else:
            detail = "status unknown"

        return f"{status_text} – {detail}"
