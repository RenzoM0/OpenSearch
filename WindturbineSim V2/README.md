# WindTurbineSim (AI-ready)

Deze app is een **simulatie** voor het OpenSearch-project.

Wat je ermee doet:
1. **CSV replay**: leest `windturbine_data.csv` en verstuurt elke paar seconden een nieuwe meting naar OpenSearch.
2. **Heartbeats**: verstuurt “ik leef nog” berichten.
3. **Attacks**: kan bewust “foute” of “verdachte” berichten sturen, zodat je die later met OpenSearch AI kunt opsporen.

Doel-index: **`turbine-ai-telemetry`** (staat in `.env`).

---

## Snel starten

### 1) Installeren
Open een terminal in de projectmap:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) `.env` instellen

Voorbeeld (pas wachtwoord/host aan):

```env
OPENSEARCH_HOST=https://localhost:9200
OPENSEARCH_USER=admin
OPENSEARCH_PASS=Patat123!
OPENSEARCH_INDEX=turbine-ai-telemetry
OPENSEARCH_VERIFY_CERTS=false

TELEMETRY_INTERVAL=5
HEARTBEAT_INTERVAL=2
CSV_PATH=data/windturbine_data.csv
```

### 3) Runnen
```powershell
uvicorn app.main:app --reload --port 8000
```

Open daarna:
- Website: `http://localhost:8000`
- Status JSON: `http://localhost:8000/api/status`

---

## Hoe gebruik je de website

1. Klik **Start streaming**  
   → de simulator gaat telemetry + heartbeat sturen.
2. Kies een **Attack profile** en klik **Trigger attack**  
   → er worden bewust “verdachte” events gemaakt.
3. Kijk in OpenSearch (Dashboards/DevTools) wat er binnenkomt.

---

# Wat gaat er naar OpenSearch?

## Telemetry event (uit CSV)
Wordt gestuurd met velden (o.a.):

- `timestamp` (nu, ISO)
- `message_type = "TELEMETRY"`
- `active_power_kw`
- `wind_speed_ms`
- `theoretical_power_kw`
- `wind_direction_deg`

## Heartbeat event
- `timestamp`
- `message_type = "HEARTBEAT"`

## Command event (bij actuator attack)
- `message_type = "COMMAND"`
- `command`
- `setpoint`
- `yaw_deg`
- `pitch_deg`

## Attack labels (handig voor filtering)
Bij attacked events worden deze velden toegevoegd:

- `is_attacked` (true/false)
- `attack_type` (`FDI` / `ACTUATOR` / `LOSS_OF_CONTACT`)
- `attack_id` (uuid)
- `attack_note` (korte tekst)

---

# Bouwtekening (hoe alles samenwerkt)

Denk in 4 blokken:

1) **UI (webpagina)**  
   - toont status  
   - stuurt knoppen-acties naar de API

2) **API (FastAPI in `app/main.py`)**  
   - `/api/status` → status voor de UI  
   - `/api/stream/start` → start streaming  
   - `/api/stream/stop` → stopt streaming  
   - `/api/attack/trigger` → zet attack “aan”

3) **Streamer (de motor) in `app/streamer.py`**  
   - leest CSV  
   - stuurt telemetry + heartbeat  
   - vraagt aan AttackEngine of hij moet “aanvallen”

4) **OpenSearch client (`app/opensearch_client.py`)**  
   - maakt verbinding met OpenSearch met `.env` settings

---

# Onderdelenlijst (bestanden & classes)

## `app/main.py` — de “bedieningsknoppen”
Doet:
- start de FastAPI webserver
- laadt `.env` (met `load_dotenv()`)
- maakt de OpenSearch client
- maakt 1 `Streamer`
- maakt API endpoints voor de UI

## `app/models.py` — “datavormpjes” voor de API
### `Status`
Het status-antwoord voor de UI:
- opensearch ok/down
- streaming running/stopped
- connectivity online/offline
- counters + last timestamps

### `AttackRequest`
Het “attack-commando” dat de UI naar de server stuurt:
- `profile`
- `duration_s`
- `messages_to_affect`

## `app/opensearch_client.py` — “stekker naar OpenSearch”
### `make_client()`
Maakt een OpenSearch client met:
- host/user/pass uit `.env`
- (optioneel) cert verificatie uit `.env`

## `app/attacks.py` — “attack aan/uit schakelaar”
### `AttackState`
Bewaart:
- is er een attack actief?
- welk type attack?
- attack_id
- tot wanneer (tijd)
- hoeveel berichten nog geraakt worden

### `AttackEngine`
De logica:
- `trigger()` → zet een attack aan (duur + aantal)
- `is_active()` → checkt of de attack nog loopt
- `should_affect_message()` → zegt “ja/nee” voor de volgende message (en telt af)

## `app/streamer.py` — “transportband” (CSV → OpenSearch)
### `Streamer`
De hoofd-motor. Doet:
- `load_csv()` → laadt CSV in geheugen
- `start()` → start 2 threads (telemetry + heartbeat)
- `stop()` → stopt de threads
- `_index_doc()` → stuurt 1 document naar OpenSearch en telt counters bij

---

# Attacks (wat doen ze)

## 1) FDI (False Data Injection)
- past `active_power_kw` aan (spike)
- zet attack labels (`is_attacked`, `attack_type=FDI`, etc.)

## 2) Command / Actuator manipulation
- stuurt extra event met `message_type=COMMAND`
- vult `command/setpoint/yaw_deg/pitch_deg`
- zet attack labels (`attack_type=ACTUATOR`)

## 3) Loss of contact
- stopt tijdelijk met telemetry + heartbeat
- UI laat `OFFLINE` zien tijdens de attack

---

# Hoe werkt power_residual_pct (het “punten”/afwijking-systeem)

Bij elke **TELEMETRY** meting sturen we twee vermogenswaarden naar OpenSearch:

- `active_power_kw` → wat de turbine *echt* levert (gemeten / uit de simulatie)
- `theoretical_power_kw` → wat de turbine *ongeveer zou moeten* leveren bij die windsnelheid (verwachte waarde)

Daarna berekenen we hoeveel de meting afwijkt van de verwachting:

### 1) Residual (verschil in kW)
```text
power_residual = active_power_kw - theoretical_power_kw
```

### 2) Residual in procenten (onze “score”)
```text
power_residual_pct = ((active_power_kw - theoretical_power_kw) / theoretical_power_kw) * 100
```

### Hoe interpreteer je de score?
- `power_residual_pct` rond **0%** → normaal (gemeten ≈ verwacht)
- **positief** (bijv. +40%) → gemeten vermogen is veel **hoger** dan verwacht (verdacht bij FDI)
- **negatief** (bijv. -60%) → gemeten vermogen is veel **lager** dan verwacht (verdacht bij actuator/setpoint misbruik)

### Waarom is dit handig voor attack-detectie?
- Bij **FDI** zie je vaak plotselinge **hoge positieve** afwijkingen.
- Bij **Actuator manipulation** (wind normaal maar vermogen 0–500kW) zie je vaak **grote negatieve** afwijkingen.

> Let op: een kleine afwijking is normaal door ruis/simulatie. Het wordt pas interessant als je een cluster ziet van grote afwijkingen in korte tijd.

---

# Snelle “werkt het?” checks (DevTools)
- verandere "model_id" naar de id van je gebruikte AI-model

## Laatste 5 minuten events
```http
GET turbine-ai-telemetry/_search
{
  "size": 10,
  "_source": ["timestamp","message_type","is_attacked","attack_type","event_text"],
  "query": { "range": { "timestamp": { "gte": "now-5m" } } },
  "sort": [{ "timestamp": "desc" }]
}
```

## AI (Neural) FDI opsporen
```http
GET turbine-ai-telemetry/_search
{
  "size": 30,
  "_source": [
    "timestamp",
    "message_type",
    "wind_speed_ms",
    "active_power_kw",
    "theoretical_power_kw",
    "power_residual_pct",
    "event_text"
  ],
  "query": {
    "bool": {
      "filter": [
        { "term": { "message_type": "TELEMETRY" } },
        { "range": { "timestamp": { "gte": "now-10m" } } }
      ],
      "must": [
        {
          "neural": {
            "event_embedding": {
              "query_text": "false data injection, manipulated sensor reading, power output inconsistent with theoretical power curve, abnormal deviation",
              "model_id": "eB6dfpsBz-P7GzKsaLlq",
              "k": 200
            }
          }
        }
      ]
    }
  },
  "sort": [{ "timestamp": "desc" }]
}
```
### Verwachte uitkomst
- Wel FDI attack: top-hits zijn TELEMETRY events rond de aanvalstijd met duidelijk hogere power_residual_pct en een zichtbare mismatch tussen active_power_kw en theoretical_power_kw.
- Geen FDI attack: je krijgt nog steeds TELEMETRY hits, maar power_residual_pct blijft meestal laag/“normaal” en je ziet geen duidelijke cluster van extreme afwijkingen.

## AI (Neural) Command/Actuator Manipulation opsporen (semantisch op “effect”)
```http
GET turbine-ai-telemetry/_search
{
  "size": 30,
  "_source": [
    "timestamp",
    "message_type",
    "wind_speed_ms",
    "active_power_kw",
    "theoretical_power_kw",
    "power_residual_pct",
    "yaw_deg",
    "pitch_deg",
    "event_text"
  ],
  "query": {
    "bool": {
      "filter": [
        { "term": { "message_type": "TELEMETRY" } },
        { "range": { "timestamp": { "gte": "now-10m" } } }
      ],
      "must": [
        {
          "neural": {
            "event_embedding": {
              "query_text": "normal wind speed but power output suddenly drops very low, turbine underperforming despite expected production, abnormal control influence on output",
              "model_id": "eB6dfpsBz-P7GzKsaLlq",
              "k": 200
            }
          }
        }
      ]
    }
  },
  "sort": [{ "timestamp": "desc" }]
}
```
### Verwachte uitkomst
- Wel actuator/command attack: top-hits zijn TELEMETRY events rond de aanvalstijd waar wind_speed_ms “normaal” is, maar active_power_kw ineens 0–500 kW wordt terwijl theoretical_power_kw veel hoger ligt. Daardoor zie je vaak een grote negatieve power_residual_pct (sterke underperformance).
- Geen actuator/command attack: resultaten blijven “normale” TELEMETRY (active power volgt theoretical power redelijk), power_residual_pct blijft meestal beperkt en je ziet geen cluster van plotselinge sterke underperformance bij normale wind.
