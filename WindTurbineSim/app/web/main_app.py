from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import get_settings

from app.domain.stream_models import StreamConfig, StreamState, StreamMode
from app.domain.wind_turbine import WindTurbine, TurbineStatus
from app.domain.messages import (
    TelemetryReading,
    MessageType,
    MessageSource,
)
from app.infrastructure.telemetry_source import (
    TelemetrySource,
    TelemetrySourceType,
    DatasetTelemetrySource,
)
from app.infrastructure.queue import TurbineMessageQueue, QueueStrategy
from app.infrastructure.opensearch_client import OpenSearchClient
from app.services.heartbeat_monitor import HeartbeatMonitor
from app.services.attack_engine import AttackEngine
from app.services.streaming_service import StreamingService

from app.web.routers_streaming import (
    router as streaming_router,
    set_streaming_service,
)
from app.web.routers_attack import router as attack_router


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

templates = Jinja2Templates(directory="app/web/templates")


# ---------------------------------------------------------------------------
# Synthetic telemetry source (for STREAM_MODE = SYNTHETIC / MIXED)
# ---------------------------------------------------------------------------


@dataclass
class SyntheticTelemetrySource(TelemetrySource):
    """
    Very simple synthetic telemetry source.

    Generates TelemetryReading objects with pseudo-realistic values.
    """

    def __init__(self, turbine: WindTurbine) -> None:
        super().__init__(
            source_id="synthetic-1",
            name="Synthetic telemetry source",
            source_type=TelemetrySourceType.SYNTHETIC,
            description="Generates synthetic wind turbine telemetry.",
            turbine=turbine,
            total_available_messages=-1,  # infinite
        )

    def initialize(self) -> None:
        self.initialized = True

    def has_more_messages(self) -> bool:
        # Synthetic source is effectively infinite
        return True

    def get_next_message(self) -> Optional[TelemetryReading]:
        if self.turbine is None:
            raise ValueError("SyntheticTelemetrySource.turbine is not configured")

        now = datetime.utcnow()
        pos = self.current_position

        # Simple pattern for demo purposes
        base_wind = 5.0 + (pos % 10) * 0.5          # 5 – 9.5 m/s
        wind_speed_ms = base_wind
        lv_active_power_kw = max(0.0, wind_speed_ms**3 / 5.0)  # rough fake curve
        theoretical_power_curve_kwh = lv_active_power_kw * 0.9
        wind_direction_deg = (pos * 15) % 360

        msg = TelemetryReading(
            message_id=f"SYN-{pos}",
            turbine=self.turbine,
            timestamp=now,
            message_type=MessageType.TELEMETRY,
            source=MessageSource.SYNTHETIC,
            wind_speed_ms=wind_speed_ms,
            lv_active_power_kw=lv_active_power_kw,
            theoretical_power_curve_kwh=theoretical_power_curve_kwh,
            wind_direction_deg=wind_direction_deg,
        )
        msg.update_content()

        self.current_position += 1
        return msg

    def reset(self) -> None:
        super().reset()
        # nothing else to reset for synthetic generator


# ---------------------------------------------------------------------------
# Wiring helper – create StreamingService and its dependencies
# ---------------------------------------------------------------------------


def build_streaming_service() -> StreamingService:
    settings = get_settings()

    # 1) Domain objects
    turbine = WindTurbine(
        turbine_id="turbine-1",
        name="Wind Turbine Alpha",
        location="Demo Site",
        rated_power_kw=2000.0,
        description="Synthetic / dataset demo turbine for WindTurbineSim.",
        status=TurbineStatus.ONLINE,
    )

    # Map STREAM_MODE string to StreamMode enum
    if settings.stream_mode == "REPLAY_DATASET":
        mode = StreamMode.REPLAY_DATASET
    elif settings.stream_mode == "MIXED":
        mode = StreamMode.MIXED
    else:
        mode = StreamMode.SYNTHETIC

    config = StreamConfig(
        enabled=False,
        data_interval_seconds=settings.stream_data_interval_seconds,
        heartbeat_interval_seconds=settings.stream_heartbeat_interval_seconds,
        mode=mode,
        target_index=settings.opensearch_index,
        batch_size=1,
        max_queue_size=1000,
        default_attack_profile_id=None,
    )

    state = StreamState()

    # 2) Infrastructure – choose telemetry source based on mode
    if mode == StreamMode.REPLAY_DATASET:
        telemetry_source = DatasetTelemetrySource(
            source_id="dataset-1",
            name="Dataset telemetry source",
            source_type=TelemetrySourceType.DATASET,
            description="Replays wind turbine telemetry from CSV dataset.",
            turbine=turbine,
            # csv_path left as default: "data/Windturbine data.csv"
        )
    else:
        # For SYNTHETIC or MIXED we currently just use synthetic.
        # (MIXED behaviour could be added later.)
        telemetry_source = SyntheticTelemetrySource(turbine=turbine)

    queue = TurbineMessageQueue(
        max_size=config.max_queue_size,
        strategy=QueueStrategy.FIFO,
    )
    heartbeat_monitor = HeartbeatMonitor(
        expected_interval_seconds=config.heartbeat_interval_seconds,
    )
    attack_engine = AttackEngine()
    opensearch_client = OpenSearchClient(
        host=settings.opensearch_host,
        port=settings.opensearch_port,
        scheme=settings.opensearch_scheme,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        default_index=settings.opensearch_index,
    )

    # --- OpenSearch connectivity + index check ---
    try:
        if not opensearch_client.ping():
            # For development: just log a warning; you could also raise an error.
            print(
                "WARNING: Could not connect to OpenSearch at "
                f"{settings.opensearch_host}:{settings.opensearch_port}"
            )
        else:
            opensearch_client.ensure_index_exists(settings.opensearch_index)
    except Exception as exc:  # noqa: BLE001
        # Clear, visible error during startup
        print(f"ERROR while checking/creating OpenSearch index: {exc}")

    # 3) Service
    service = StreamingService(
        config=config,
        state=state,
        telemetry_source=telemetry_source,
        queue=queue,
        heartbeat_monitor=heartbeat_monitor,
        attack_engine=attack_engine,
        opensearch_client=opensearch_client,
    )

    return service


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """
    app = FastAPI(
        title="WindTurbineSim",
        description="Wind turbine telemetry and attack simulation using OpenSearch.",
        version="0.1.0",
    )

    # Mount static files (CSS, JS)
    app.mount(
        "/static",
        StaticFiles(directory="app/web/static"),
        name="static",
    )

    # Build and register the StreamingService so routers can use it
    streaming_service = build_streaming_service()
    set_streaming_service(streaming_service)

    # Include API routers
    app.include_router(streaming_router)
    app.include_router(attack_router)

    # Root API endpoint
    @app.get("/")
    async def root() -> dict:
        return {
            "message": (
                "WindTurbineSim backend is running. "
                "Use /ui for the dashboard, /health, /stream/* and /attack/* for API control."
            )
        }

    # Health endpoint
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    # UI dashboard endpoint
    @app.get("/ui", response_class=HTMLResponse)
    async def ui_dashboard(request: Request) -> HTMLResponse:
        settings = get_settings()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "app_env": settings.app_env,
            },
        )

    return app


# Uvicorn entrypoint:
# uvicorn app.web.main_app:app --reload
app = create_app()
