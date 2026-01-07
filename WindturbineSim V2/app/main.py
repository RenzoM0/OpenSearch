import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import Status, AttackRequest
from .opensearch_client import make_client
from .streamer import Streamer


app = FastAPI()

app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

client = make_client()

INDEX = os.getenv("OPENSEARCH_INDEX", "turbine-ai-telemetry")
CSV_PATH = os.getenv("CSV_PATH", "data/windturbine_data.csv")
TELEMETRY_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "5"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "2"))

streamer = Streamer(
    client=client,
    index_name=INDEX,
    csv_path=CSV_PATH,
    telemetry_interval_s=TELEMETRY_INTERVAL,
    heartbeat_interval_s=HEARTBEAT_INTERVAL,
)

def opensearch_ok() -> bool:
    try:
        client.info()
        return True
    except Exception:
        return False


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/status", response_model=Status)
def status():
    s = Status(
        opensearch_ok=opensearch_ok(),
        stream_running=streamer.running,
        connectivity=streamer.connectivity,
        target_index=INDEX,
        telemetry_interval_s=TELEMETRY_INTERVAL,
        heartbeat_interval_s=HEARTBEAT_INTERVAL,
        dataset_position=streamer.pos,
        total_messages=streamer.total_messages,
        attacked_messages=streamer.attacked_messages,
        last_telemetry_iso=streamer.last_telemetry_iso,
        last_heartbeat_iso=streamer.last_heartbeat_iso,
    )
    return s


@app.post("/api/stream/start")
def start_stream():
    streamer.start()
    return JSONResponse({"ok": True})


@app.post("/api/stream/stop")
def stop_stream():
    streamer.stop()
    return JSONResponse({"ok": True})


@app.post("/api/attack/trigger")
def trigger_attack(req: AttackRequest):
    streamer.trigger_attack(req.profile, req.duration_s, req.messages_to_affect)
    return JSONResponse({"ok": True, "profile": req.profile})
