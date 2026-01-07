import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class AttackState:
    active: bool = False
    attack_type: Optional[str] = None
    attack_id: Optional[str] = None
    until_ts: float = 0.0
    remaining_messages: int = 0


class AttackEngine:
    def __init__(self):
        self.state = AttackState()

    def trigger(self, attack_type: str, duration_s: int, messages_to_affect: int):
        self.state.active = True
        self.state.attack_type = attack_type
        self.state.attack_id = str(uuid.uuid4())
        self.state.until_ts = time.time() + max(1, duration_s)
        self.state.remaining_messages = max(0, messages_to_affect)

    def is_active(self) -> bool:
        if not self.state.active:
            return False
        if time.time() > self.state.until_ts:
            self.state.active = False
            return False
        return True

    def should_affect_message(self) -> bool:
        if not self.is_active():
            return False
        if self.state.remaining_messages <= 0:
            return False
        self.state.remaining_messages -= 1
        return True
