# WindTurbineSim

WindTurbineSim is a small simulation backend + dashboard that **streams wind turbine SCADA data into OpenSearch** and lets you simulate **three cyber-attack scenarios**:

1. **Loss of Contact** – heartbeats disappear, monitoring goes “offline”.
2. **False Data Injection (FDI) – Power Bias (Version B)** – wind stays the same, reported power is subtly wrong.
3. **Command / Actuator Manipulation** – power suddenly drops to 0 or flaps between 0–500 kW while wind is good.

The goal is **not** only to send data, but to create **attack patterns you can recognise and hunt for in OpenSearch** (dashboards, correlations, alerts, etc.).

---

## 1. Tech stack & structure

**Tech stack**

- **Backend:** Python, FastAPI, Uvicorn  
- **Frontend:** HTML + vanilla JS, minimal CSS  
- **Search / analytics:** OpenSearch  
- **Containerisation:** Docker + (optional) Docker Compose  
- **Config:** `.env` file + Pydantic `Settings`

**Folder structure (inside `WindTurbineSim/`)**

```text
WindTurbineSim/
├─ app/
│  ├─ domain/          # Pure domain models
│  │  ├─ wind_turbine.py
│  │  ├─ messages.py
│  │  ├─ stream_models.py
│  │  └─ attacks.py
│  ├─ infrastructure/  # Integration with CSV, OpenSearch, queues
│  │  ├─ telemetry_source.py
│  │  ├─ opensearch_client.py
│  │  └─ queue.py
│  ├─ services/        # Orchestration / business logic
│  │  ├─ streaming_service.py
│  │  └─ attack_engine.py
│  └─ web/             # FastAPI web / API layer + UI
│     ├─ main_app.py
│     ├─ routers_streaming.py
│     ├─ routers_attack.py
│     ├─ templates/
│     │  ├─ base.html
│     │  └─ dashboard.html
│     └─ static/
│        ├─ css/main.css
│        └─ js/dashboard.js
├─ config/
│  ├─ __init__.py      # get_settings()
│  └─ settings.py      # Pydantic Settings class
├─ data/
│  └─ windturbine_data.csv  # Input dataset (SCADA-like)
├─ requirements.txt
├─ Dockerfile
└─ README.md           
