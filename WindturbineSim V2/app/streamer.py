import csv
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from annotated_types import doc
from opensearchpy import OpenSearch

from .attacks import AttackEngine


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Streamer:
    def __init__(self, client: OpenSearch, index_name: str, csv_path: str, telemetry_interval_s: int, heartbeat_interval_s: int):
        self.client = client
        self.index = index_name
        self.csv_path = csv_path
        self.telemetry_interval_s = telemetry_interval_s
        self.heartbeat_interval_s = heartbeat_interval_s

        self.rows: List[Dict] = []
        self.pos = 0

        self.running = False
        self.lock = threading.Lock()

        self.attack_engine = AttackEngine()

        self.total_messages = 0
        self.attacked_messages = 0
        self.last_telemetry_iso: Optional[str] = None
        self.last_heartbeat_iso: Optional[str] = None

        self.connectivity = "ONLINE"  # OFFLINE during loss-of-contact

        self._telemetry_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

    def load_csv(self):
        # CSV headers:
        # Date/Time, LV ActivePower (kW), Wind Speed (m/s), Theoretical_Power_Curve (KWh), Wind Direction (°)
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.rows = list(reader)
        self.pos = 0

    def _index_doc(self, doc: Dict):
        self.client.index(index=self.index, body=doc)
        self.total_messages += 1
        if doc.get("is_attacked"):
            self.attacked_messages += 1

    def start(self):
        with self.lock:
            if self.running:
                return
            if not self.rows:
                self.load_csv()
            self.running = True

        self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._telemetry_thread.start()
        self._heartbeat_thread.start()

    def stop(self):
        with self.lock:
            self.running = False

    def trigger_attack(self, profile: str, duration_s: int, messages_to_affect: int):
        self.attack_engine.trigger(profile, duration_s, messages_to_affect)

    def _telemetry_loop(self):
        while True:
            with self.lock:
                if not self.running:
                    break

            # Loss of contact: geen telemetry sturen als die attack actief is
            if self.attack_engine.is_active() and self.attack_engine.state.attack_type == "LOSS_OF_CONTACT":
                self.connectivity = "OFFLINE"
                time.sleep(1)
                continue
            else:
                self.connectivity = "ONLINE"

            row = self.rows[self.pos]
            self.pos = (self.pos + 1) % len(self.rows)

            # Map CSV -> index fields
            doc = {
                "timestamp": now_iso(),
                "message_type": "TELEMETRY",
                "active_power_kw": float(row["LV ActivePower (kW)"]),
                "wind_speed_ms": float(row["Wind Speed (m/s)"]),
                "theoretical_power_kw": float(row["Theoretical_Power_Curve (KWh)"]),
                "wind_direction_deg": float(row["Wind Direction (°)"]),
            }

            # Apply attack if active
            attacked = False
            if self.attack_engine.should_affect_message():
                at = self.attack_engine.state.attack_type
                if at == "FDI":
                    # FDI: spike op active power
                    doc["active_power_kw"] = doc["active_power_kw"] * 1.35 + 200 
                    attacked = True

                elif at == "ACTUATOR":
                    # Actuator manipulation: wind blijft normaal, maar vermogen zakt ineens naar 0-500 kW
                    low_power = round(random.uniform(0, 500), 3)
                    doc["active_power_kw"] = low_power

                    # (optioneel) context in telemetry zetten
                    doc["yaw_deg"] = 999.0
                    doc["pitch_deg"] = -45.0

                    attacked = True

                    cmd_doc = {
                        "timestamp": now_iso(),
                        "message_type": "COMMAND",
                        "command": "SET_SETPOINT",
                        "setpoint": low_power,
                        "yaw_deg": 999.0,
                        "pitch_deg": -45.0,
                        "is_attacked": True,
                        "attack_type": "ACTUATOR",
                        "attack_id": self.attack_engine.state.attack_id,
                        "attack_note": "Actuator manipulated: setpoint forced low, yaw/pitch abnormal."
                    }
                    self._index_doc(cmd_doc)
                    self.last_telemetry_iso = doc["timestamp"]

            if attacked:
                doc["is_attacked"] = True
                doc["attack_type"] = "FDI"
                doc["attack_id"] = self.attack_engine.state.attack_id
                doc["attack_note"] = "Active power manipulated (simulated FDI)."
            else:
                doc["is_attacked"] = False

            self._index_doc(doc)
            self.last_telemetry_iso = doc["timestamp"]

            time.sleep(self.telemetry_interval_s)

    def _heartbeat_loop(self):
        while True:
            with self.lock:
                if not self.running:
                    break

            # Loss of contact: geen heartbeats sturen
            if self.attack_engine.is_active() and self.attack_engine.state.attack_type == "LOSS_OF_CONTACT":
                self.connectivity = "OFFLINE"
                time.sleep(1)
                continue
            else:
                self.connectivity = "ONLINE"

            hb = {
                "timestamp": now_iso(),
                "message_type": "HEARTBEAT",
                "is_attacked": False
            }
            self._index_doc(hb)
            self.last_heartbeat_iso = hb["timestamp"]

            time.sleep(self.heartbeat_interval_s)
