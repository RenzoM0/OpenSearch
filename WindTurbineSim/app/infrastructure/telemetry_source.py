from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Any
from datetime import datetime
import csv
import os

from app.domain.messages import (
    TurbineMessage,
    TelemetryReading,
    MessageType,
    MessageSource,
)
from app.domain.wind_turbine import WindTurbine


class TelemetrySourceType(Enum):
    """Type of telemetry source."""

    DATASET = auto()    # e.g. replay from CSV
    SYNTHETIC = auto()  # generated data
    MIXED = auto()      # combination of both


@dataclass
class TelemetrySource(ABC):
    """
    Abstract base class for all telemetry sources.

    A telemetry source is responsible for providing TurbineMessage instances
    (typically TelemetryReading and sometimes HeartbeatMessage) to the
    StreamingService.
    """

    source_id: str
    name: str
    source_type: TelemetrySourceType
    description: str = ""

    turbine: Optional[WindTurbine] = None

    total_available_messages: int = -1  # -1 = unknown / infinite
    current_position: int = 0
    initialized: bool = field(default=False, init=False)

    @abstractmethod
    def initialize(self) -> None:
        """
        Prepare the source for use.

        For dataset sources, this might open a file and count rows.
        For synthetic sources, this might initialise random generators.
        """
        self.initialized = True

    @abstractmethod
    def get_next_message(self) -> Optional[TurbineMessage]:
        """
        Return the next message from this source and advance the position.

        Returns:
            - TurbineMessage: next message in sequence
            - None: if no more messages are available (for finite sources)
        """
        raise NotImplementedError

    @abstractmethod
    def has_more_messages(self) -> bool:
        """
        Return True if there are more messages available from this source.

        For infinite/synthetic sources, this can always return True.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the source to its initial state (start from the beginning).

        For dataset sources, this rewinds to the first record.
        For synthetic sources, this resets internal counters/state.
        """
        self.current_position = 0

    def skip(self, count: int) -> None:
        """
        Skip a number of messages from this source.

        Default implementation repeatedly calls get_next_message(); concrete
        sources can override with a more efficient implementation if needed.
        """
        if count <= 0:
            return

        skipped = 0
        while skipped < count and self.has_more_messages():
            _ = self.get_next_message()
            skipped += 1

    def get_progress(self) -> float:
        """
        Return progress through the source as a value between 0.0 and 1.0.

        For synthetic/infinite sources (total_available_messages < 0),
        this returns -1.0 to indicate "not applicable".
        """
        if self.total_available_messages <= 0:
            return -1.0

        return min(
            1.0,
            max(0.0, self.current_position / float(self.total_available_messages)),
        )


# ---------------------------------------------------------------------------
# Dataset-backed telemetry source (CSV replay)
# ---------------------------------------------------------------------------


@dataclass
class DatasetTelemetrySource(TelemetrySource):
    """
    Telemetry source that replays messages from a CSV dataset.

    This is designed for the 'Windturbine data.csv' structure:
    - Date/Time
    - LV ActivePower (kW)
    - Wind Speed (m/s)
    - Theoretical_Power_Curve (KWh)
    - Wind Direction (°)

    We *ignore* the original timestamp column and always use datetime.utcnow()
    so the stream behaves like live telemetry.
    """

    csv_path: str = "data/Windturbine data.csv"

    _rows: List[Dict[str, Any]] = field(default_factory=list, init=False)

    def initialize(self) -> None:
        """Load the CSV rows into memory and normalise column names."""
        if self.initialized:
            return

        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"Dataset CSV not found: {self.csv_path}")

        rows: List[Dict[str, Any]] = []

        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Normalise headers (strip whitespace + BOM)
            raw_headers = reader.fieldnames or []
            header_map = {
                (h or ""): (h or "").strip().lstrip("\ufeff") for h in raw_headers
            }

            for raw_row in reader:
                normalized_row: Dict[str, Any] = {}
                for raw_key, value in raw_row.items():
                    if raw_key is None:
                        continue
                    norm_key = header_map.get(raw_key, raw_key).strip()
                    normalized_row[norm_key] = value
                rows.append(normalized_row)

        self._rows = rows
        self.total_available_messages = len(self._rows)
        self.current_position = 0

        super().initialize()  # sets initialized = True

    def has_more_messages(self) -> bool:
        """Return True when there are still rows left in the dataset."""
        return self.current_position < len(self._rows)

    def get_next_message(self) -> Optional[TurbineMessage]:
        """
        Convert the next CSV row into a TelemetryReading.

        Returns None when the dataset is exhausted.
        """
        if not self.initialized:
            self.initialize()

        if not self.has_more_messages():
            return None

        if self.turbine is None:
            raise ValueError("DatasetTelemetrySource.turbine is not configured")

        row_index = self.current_position
        row = self._rows[row_index]
        self.current_position += 1

        # Column names from the windturbine CSV.
        # We ignore the original timestamp and always use "now"
        # so the stream behaves like live data.
        wind_speed_str = (row.get("Wind Speed (m/s)") or "").strip()
        active_power_str = (row.get("LV ActivePower (kW)") or "").strip()
        theoretical_str = (row.get("Theoretical_Power_Curve (KWh)") or "").strip()
        wind_dir_str = (row.get("Wind Direction (°)") or "").strip()

        # Use current time as the telemetry timestamp to simulate live data
        timestamp = datetime.utcnow()

        # Parse numeric fields with safe fallbacks
        def to_float(value: str, default: float = 0.0) -> float:
            try:
                return float(value)
            except Exception:
                return default

        wind_speed_ms = to_float(wind_speed_str, 0.0)
        lv_active_power_kw = to_float(active_power_str, 0.0)
        theoretical_power_curve_kwh = to_float(theoretical_str, 0.0)
        wind_direction_deg = to_float(wind_dir_str, 0.0)

        msg = TelemetryReading(
            message_id=f"CSV-{row_index}",
            turbine=self.turbine,
            timestamp=timestamp,
            message_type=MessageType.TELEMETRY,
            source=MessageSource.DATASET,
            wind_speed_ms=wind_speed_ms,
            lv_active_power_kw=lv_active_power_kw,
            theoretical_power_curve_kwh=theoretical_power_curve_kwh,
            wind_direction_deg=wind_direction_deg,
        )
        msg.update_content()

        # TelemetryReading is a subclass of TurbineMessage, so this type matches
        return msg

    def reset(self) -> None:
        """Rewind to the first row in the dataset."""
        super().reset()
        self.current_position = 0
