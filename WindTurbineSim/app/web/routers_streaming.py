from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.streaming_service import StreamingService
from app.domain.stream_models import StreamConfig, StreamState

router = APIRouter(prefix="/stream", tags=["streaming"])

# ---------------------------------------------------------------------------
# Simple global holder – will be wired from main_app later.
# ---------------------------------------------------------------------------

_streaming_service: Optional[StreamingService] = None


def set_streaming_service(service: StreamingService) -> None:
    """
    Configure the global StreamingService instance.

    Call this from main_app.py when you have created the service.
    """
    global _streaming_service
    _streaming_service = service


def get_streaming_service() -> StreamingService:
    """
    FastAPI dependency to inject the StreamingService.

    Raises 500 if the service has not been configured yet.
    """
    if _streaming_service is None:
        raise HTTPException(
            status_code=500,
            detail="StreamingService is not configured yet.",
        )
    return _streaming_service


# ---------------------------------------------------------------------------
# Pydantic models for requests / responses
# ---------------------------------------------------------------------------


class StreamConfigUpdate(BaseModel):
    """Partial update model for StreamConfig."""

    enabled: Optional[bool] = None
    data_interval_seconds: Optional[int] = None
    heartbeat_interval_seconds: Optional[int] = None
    target_index: Optional[str] = None
    batch_size: Optional[int] = None
    max_queue_size: Optional[int] = None


class StreamStatusResponse(BaseModel):
    """Simplified view of StreamState + config for the API."""

    status: str
    connectivity_status: str

    total_messages_sent: int
    total_attacked_messages: int

    last_telemetry_sent_at: Optional[datetime]
    last_heartbeat_sent_at: Optional[datetime]

    current_dataset_position: int

    # Config snapshot
    config: StreamConfig

    # OpenSearch health
    opensearch_connected: bool
    opensearch_last_error: Optional[str]
    opensearch_index: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StreamStatusResponse)
def get_status(service: StreamingService = Depends(get_streaming_service)) -> StreamStatusResponse:
    """
    Get current streaming status + configuration + OpenSearch health.
    """
    state: StreamState = service.state
    config: StreamConfig = service.config

    client = service.opensearch_client

    # Ping OpenSearch on each status call so the UI can see live health
    connected = client.ping()
    last_error = client.get_last_error()
    index_name = client.default_index

    return StreamStatusResponse(
        status=state.status.name,
        connectivity_status=state.connectivity_status.name,
        total_messages_sent=state.total_messages_sent,
        total_attacked_messages=state.total_attacked_messages,
        last_telemetry_sent_at=state.last_telemetry_sent_at,
        last_heartbeat_sent_at=state.last_heartbeat_sent_at,
        current_dataset_position=state.current_dataset_position,
        config=config,
        opensearch_connected=connected,
        opensearch_last_error=last_error,
        opensearch_index=index_name,
    )


@router.post("/start")
def start_streaming(service: StreamingService = Depends(get_streaming_service)) -> dict:
    """
    Start streaming using current configuration.
    """
    service.start()
    return {"status": "started", "summary": service.get_status_summary()}


@router.post("/stop")
def stop_streaming(service: StreamingService = Depends(get_streaming_service)) -> dict:
    """
    Stop streaming.
    """
    service.stop()
    return {"status": "stopped", "summary": service.get_status_summary()}


@router.post("/tick")
def tick_streaming(service: StreamingService = Depends(get_streaming_service)) -> dict:
    """
    Perform one streaming 'tick'.
    """
    service.tick()
    return {"status": "ok", "summary": service.get_status_summary()}


@router.get("/config", response_model=StreamConfig)
def get_config(service: StreamingService = Depends(get_streaming_service)) -> StreamConfig:
    """
    Get the current StreamConfig.
    """
    return service.config


@router.post("/config")
def update_config(
    update: StreamConfigUpdate,
    service: StreamingService = Depends(get_streaming_service),
) -> dict:
    """
    Update parts of the StreamConfig.

    Only fields that are provided in the body are changed.
    """
    config = service.config

    if update.enabled is not None:
        if update.enabled:
            config.enable()
        else:
            config.disable()

    if update.data_interval_seconds is not None:
        config.data_interval_seconds = update.data_interval_seconds

    if update.heartbeat_interval_seconds is not None:
        config.heartbeat_interval_seconds = update.heartbeat_interval_seconds

    if update.target_index is not None:
        config.set_target_index(update.target_index)

    if update.batch_size is not None:
        config.batch_size = update.batch_size

    if update.max_queue_size is not None:
        config.max_queue_size = update.max_queue_size

    config.last_updated_at = datetime.utcnow()

    return {
        "status": "updated",
        "valid": config.validate(),
        "config": config,
    }
