# WindTurbineSim

WindTurbineSim is a small FastAPI application that simulates a wind turbine
sending telemetry and heartbeat messages into an OpenSearch index.

!!! FOR DASHBOARD WINDTURBINESIM GO TO url/ui !!!

It’s built as a teaching/demo tool:

- normal “healthy” turbine behaviour
- optional CSV replay of real turbine data
- attack simulation layer (message suppression / manipulation)
- OpenSearch + Dashboards to explore the data

---

## Features

- **FastAPI backend** with a simple web dashboard (`/ui`)
- **Streaming service** that:
  - generates synthetic telemetry **or**
  - replays real data from `data/windturbine_data.csv`
- **Heartbeat messages** to simulate “keep-alive” signals
- **OpenSearch integration**
  - configurable host/port/scheme
  - automatic index creation
- **Attack engine (WIP)**
  - framework for loss-of-contact and data manipulation attacks
- **Docker image** so teammates can run it without installing Python
- **Docker Compose integration** with an OpenSearch cluster (in parent folder)

---

## Requirements

For local (non-Docker) development:

- Python 3.11+
- A running OpenSearch cluster (e.g. via Docker)
- Node/JS is not required – frontend is plain HTML/JS served by FastAPI

For the Docker version:

- Docker Desktop (or any recent Docker engine)
- Optional: docker compose if you run it together with OpenSearch

---

## Project structure

```text
WindTurbineSim/
  app/
    domain/          # Core domain models (turbine, messages, stream config, attacks)
    infrastructure/  # OpenSearch client, telemetry sources, queues
    services/        # StreamingService, AttackEngine, HeartbeatMonitor
    web/             # FastAPI app, routers, templates, static JS/CSS
  config/
    __init__.py
    settings.py      # AppSettings + get_settings() (reads .env)
  data/
    Windturbine data.csv  # Source dataset for REPLAY_DATASET mode
  Dockerfile
  requirements.txt
  README.md

