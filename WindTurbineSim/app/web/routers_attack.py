from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import get_settings
from app.services.streaming_service import StreamingService
from app.domain.attacks import (
    AttackProfile,
    AttackEvent,
    AttackCategory,
    ManipulationType,
    DurationMode,
    AttackEventStatus,
)
from app.web.routers_streaming import get_streaming_service


router = APIRouter(prefix="/attack", tags=["attacks"])


# ---------------------------------------------------------------------------
# In-memory registry of available AttackProfiles
# ---------------------------------------------------------------------------


def _create_default_profiles() -> Dict[str, AttackProfile]:
    """Create the default attack profiles for the simulator."""
    profiles: Dict[str, AttackProfile] = {}

    settings = get_settings()
    loss_contact_duration = settings.loss_contact_duration_seconds
    fdi_messages_to_affect = settings.fdi_messages_to_affect_default
    cmd_actuator_duration_seconds = settings.cmd_actuator_duration_seconds

    # 1) Loss of Contact – suppress heartbeats for a configurable time window
    #
    # Scenario 1: Loss of contact / missing heartbeats. This uses
    # MESSAGE_SUPPRESSION + TIME_WINDOW and is implemented via
    # AttackEngine.should_suppress().
    profiles["LOSS_CONTACT_10MIN"] = AttackProfile(
        attack_profile_id="LOSS_CONTACT_10MIN",
        name=f"Loss of Contact ({loss_contact_duration} seconds)",
        description=(
            "Simulates loss of contact by suppressing heartbeat messages "
            f"for about {loss_contact_duration} seconds. The turbine keeps "
            "running, but monitoring stops seeing heartbeats."
        ),
        attack_category=AttackCategory.MESSAGE_SUPPRESSION,
        manipulation_type=None,
        duration_mode=DurationMode.TIME_WINDOW,
        default_messages_to_affect=0,
        default_duration_seconds=loss_contact_duration,
        fields_affected="heartbeats (suppressed)",
        severity=5,
        enabled=True,
    )

    # 2) False Data Injection – Version B (±10–15% power bias)
    #
    # Scenario 3 in your write-up: wind speed stays the same, but
    # LV ActivePower is biased by about ±10–15%. This is a classic FDI
    # pattern: the relationship between wind and power is subtly wrong.
    #
    # Implemented in AttackEngine as:
    #   - attack_category = DATA_MANIPULATION
    #   - manipulation_type = MULTIPLY
    #
    # AttackEngine MULTIPLY branch:
    #   - leaves wind_speed_ms unchanged
    #   - scales lv_active_power_kw by a random factor in [0.85, 1.15]
    profiles["FDI_POWER_BIAS_V2"] = AttackProfile(
        attack_profile_id="FDI_POWER_BIAS_V2",
        name="False Data Injection – Power Bias (Version B)",
        description=(
            "FDI Version B: keeps wind speed unchanged but biases LV ActivePower "
            "by roughly ±10–15%. In OpenSearch this weakens the correlation "
            "between wind speed and power and shifts the power curve."
        ),
        attack_category=AttackCategory.DATA_MANIPULATION,
        manipulation_type=ManipulationType.MULTIPLY,
        duration_mode=DurationMode.MULTIPLE_MESSAGES,
        default_messages_to_affect=fdi_messages_to_affect,  # affects ~50 telemetry messages by default
        default_duration_seconds=0,
        fields_affected="lv_active_power_kw",
        severity=4,
        enabled=True,
    )

    # 3) Command / Actuator Manipulation – remote stop / on–off flapping
    #
    # Scenario 2 in your write-up: attacker sends malicious commands to
    # the turbine controller: stop, repeated on/off, etc. Wind remains high
    # (e.g. 8–12 m/s) but LV ActivePower periodically drops to 0 or low values.
    #
    # Implemented in AttackEngine as:
    #   - attack_category = DATA_MANIPULATION
    #   - manipulation_type = OVERRIDE
    #
    # AttackEngine OVERRIDE branch:
    #   - ~60% of the time: lv_active_power_kw = 0.0 (complete stop)
    #   - ~40% of the time: lv_active_power_kw ∈ [0, 500] kW

    profiles["CMD_ACTUATOR_MANIP_V1"] = AttackProfile(
        attack_profile_id="CMD_ACTUATOR_MANIP_V1",
        name="Command / Actuator Manipulation",
        description=(
            "Simulates remote command or actuator manipulation: LV ActivePower "
            "drops to 0 kW or flaps between 0 and ~500 kW while wind speed "
            "remains high. Models short control disruptions or intentional stops."
        ),
        attack_category=AttackCategory.DATA_MANIPULATION,
        manipulation_type=ManipulationType.OVERRIDE,
        duration_mode=DurationMode.TIME_WINDOW,
        default_messages_to_affect=0,
        default_duration_seconds=cmd_actuator_duration_seconds,
        fields_affected="lv_active_power_kw",
        severity=5,
        enabled=True,
    )

    return profiles


ATTACK_PROFILES: Dict[str, AttackProfile] = _create_default_profiles()


# ---------------------------------------------------------------------------
# Pydantic models for API I/O
# ---------------------------------------------------------------------------


class AttackProfileResponse(BaseModel):
    attack_profile_id: str
    name: str
    description: str
    attack_category: str
    manipulation_type: Optional[str]
    duration_mode: str
    default_messages_to_affect: int
    default_duration_seconds: int
    fields_affected: str
    severity: int
    enabled: bool


class AttackEventResponse(BaseModel):
    attack_event_id: str
    profile_id: str
    profile_name: str
    status: str
    triggered_by: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    affected_messages_count: int
    notes: str


class TriggerAttackRequest(BaseModel):
    attack_profile_id: str
    messages_to_affect: Optional[int] = None
    duration_seconds: Optional[int] = None
    triggered_by: Optional[str] = "user"


class StopAttackRequest(BaseModel):
    attack_event_id: Optional[str] = None
    reason: Optional[str] = "Stopped by user"


def _profile_to_response(profile: AttackProfile) -> AttackProfileResponse:
    return AttackProfileResponse(
        attack_profile_id=profile.attack_profile_id,
        name=profile.name,
        description=profile.description,
        attack_category=profile.attack_category.name,
        manipulation_type=profile.manipulation_type.name
        if profile.manipulation_type
        else None,
        duration_mode=profile.duration_mode.name,
        default_messages_to_affect=profile.default_messages_to_affect,
        default_duration_seconds=profile.default_duration_seconds,
        fields_affected=profile.fields_affected,
        severity=profile.severity,
        enabled=profile.enabled,
    )


def _event_to_response(event: AttackEvent) -> AttackEventResponse:
    return AttackEventResponse(
        attack_event_id=event.attack_event_id,
        profile_id=event.profile.attack_profile_id,
        profile_name=event.profile.name,
        status=event.status.name,
        triggered_by=event.triggered_by,
        start_time=event.start_time,
        end_time=event.end_time,
        affected_messages_count=event.affected_messages_count,
        notes=event.notes,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/profiles", response_model=List[AttackProfileResponse])
def list_attack_profiles() -> List[AttackProfileResponse]:
    """
    List all available attack profiles.

    These are the options the UI can show in a dropdown.
    """
    return [_profile_to_response(p) for p in ATTACK_PROFILES.values()]


@router.get("/profiles/{profile_id}", response_model=AttackProfileResponse)
def get_attack_profile(profile_id: str) -> AttackProfileResponse:
    """Get a single attack profile by id."""
    profile = ATTACK_PROFILES.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="AttackProfile not found")

    return _profile_to_response(profile)


@router.post("/trigger", response_model=AttackEventResponse)
def trigger_attack(
    request: TriggerAttackRequest,
    service: StreamingService = Depends(get_streaming_service),
) -> AttackEventResponse:
    """
    Trigger an attack using one of the predefined AttackProfiles.

    The actual logic of applying the attack is handled by StreamingService
    and AttackEngine.
    """
    profile = ATTACK_PROFILES.get(request.attack_profile_id)
    if profile is None or not profile.enabled:
        raise HTTPException(
            status_code=404,
            detail="AttackProfile not found or disabled",
        )

    event = service.trigger_attack(
        profile=profile,
        messages_to_affect=request.messages_to_affect,
        duration_seconds=request.duration_seconds,
        triggered_by=request.triggered_by or "user",
    )

    return _event_to_response(event)


@router.post("/stop", response_model=AttackEventResponse)
def stop_attack(
    request: StopAttackRequest,
    service: StreamingService = Depends(get_streaming_service),
) -> AttackEventResponse:
    """
    Manually stop the currently active attack (or a specific AttackEvent by id).

    If no attack_event_id is given, the most recent ACTIVE event is stopped.
    """
    event = service.stop_active_attack(
        attack_event_id=request.attack_event_id,
        reason=request.reason or "Stopped by user",
    )
    if event is None:
        raise HTTPException(status_code=404, detail="No active attack to stop")

    return _event_to_response(event)


@router.get("/events", response_model=List[AttackEventResponse])
def list_attack_events(
    service: StreamingService = Depends(get_streaming_service),
) -> List[AttackEventResponse]:
    """
    List all recorded attack events (history).
    """
    return [_event_to_response(ev) for ev in service.attack_events]


@router.get("/events/{event_id}", response_model=AttackEventResponse)
def get_attack_event(
    event_id: str,
    service: StreamingService = Depends(get_streaming_service),
) -> AttackEventResponse:
    """Get details of a single attack event by id."""
    for ev in service.attack_events:
        if ev.attack_event_id == event_id:
            return _event_to_response(ev)

    raise HTTPException(status_code=404, detail="AttackEvent not found")
