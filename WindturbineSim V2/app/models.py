from pydantic import BaseModel
from typing import Optional


class Status(BaseModel):
    environment: str = "development"
    opensearch_ok: bool
    stream_running: bool
    connectivity: str  # ONLINE / OFFLINE

    target_index: str
    telemetry_interval_s: int
    heartbeat_interval_s: int
    dataset_position: int

    total_messages: int
    attacked_messages: int

    last_telemetry_iso: Optional[str] = None
    last_heartbeat_iso: Optional[str] = None


class AttackRequest(BaseModel):
    profile: str  # "FDI" | "ACTUATOR" | "LOSS_OF_CONTACT"
    duration_s: int = 30
    messages_to_affect: int = 10
