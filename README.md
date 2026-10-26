# 🌾 Agrisathi — AI-powered decision intelligence for Indian agriculture

Agrisathi turns scattered agricultural signals (weather, soil, crop stage, pest/disease risk and mandi prices) into **one ranked list of farm actions**, explains why each was suggested, and learns from farmer feedback.

> Recommendations are decision support, not validated agronomic prescriptions. Farmers should confirm doses and treatments with their KVK or Krishi officer.

This repository implements **Phase 1 + market intelligence** from the project deck (`Agrisathi_Project_Presentation.pptx`).

---

## How it works

```
DATA LAYER                       INTELLIGENCE LAYER                    APPLICATION & FEEDBACK
Open-Meteo weather + soil  ─┐    features.py   → one FarmContext       dashboard / decisions page
Soil Health Card values    ─┤    pest_risk.py  → disease risk           Accept / Not useful / Done + outcome
Crop calendar (stage)      ─┼──▶ rules.yaml    → candidate actions ──▶  feedback table
Agmarknet / sample prices  ─┘    fusion.py     → conflict resolution        │
                                 ranker.py     → ranked actions  ◀──────────┘ acceptance rate per rule
```

- **Data ingestion** (`backend/app/ingestion/`): 7-day forecast and modelled soil moisture from Open-Meteo (no key needed, cached for 1 h); Soil Health Card N/P/K, pH and OC rated Low/Medium/High; crop stage from sowing date; mandi prices from data.gov.in (Agmarknet), with built-in sample prices when no key is set.
- **Decision fusion** (`backend/app/engine/`): all signals are normalised into one `FarmContext`. Declarative rules in `knowledge/rules.yaml` fire against it, conflicting actions are suppressed (for example, "delay irrigation" overrides "irrigate now", and heavy rain postpones fertiliser), and the rest are ranked by `urgency × impact × confidence × feedback prior`.
- **Closed loop**: farmers accept, reject or mark actions done (with an outcome note and a rating). Each rule's smoothed acceptance rate nudges its future ranking, and `/api/evaluation/summary` reports acceptance metrics.
- **AI assistant**: the chat page sends text and photos to OpenAI **from the server** (the key never reaches the browser), with the farm's current context and recommendations attached. Recommendations are also rewritten into Malayalam or Hindi for farmers who choose those languages.

Worked example (slide 10, covered by a test): tomato at flowering, low N, adequate moisture, high rain chance, moderate disease risk and rising prices gives **1. Delay irrigation → 2. Apply nitrogen per guidance → 3. Monitor disease risk → 4. Consider market timing**.

---

## Run locally

Requirements: Python 3.11+ and PostgreSQL running locally.

```bash
# 1. virtualenv + dependencies (from the project root)
py -3.12 -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt

# 2. database
createdb -U postgres agrisathi

# 3. configuration: copy .env.example to .env and set DATABASE_URL, JWT_SECRET
#    (OPENAI_API_KEY and DATA_GOV_API_KEY are optional)
copy .env.example .env

# 4. schema + demo data (from backend/)
cd backend
..\.venv\Scripts\alembic upgrade head
..\.venv\Scripts\python -m app.seed

# 5. start: serves both the API (/api) and the frontend
..\.venv\Scripts\uvicorn app.main:app --reload
```

Open http://localhost:8000. The seed creates a demo farmer (credentials are in `backend/app/seed.py`) with a tomato plot near Bengaluru. You can also register a new account and set up your own farm.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | e.g. `postgresql+psycopg://postgres:<pw>@localhost:5432/agrisathi` |
| `JWT_SECRET` | yes | signs login tokens |
| `OPENAI_API_KEY` | no | AI chat and non-English recommendation text; without it the chat returns a notice |
| `OPENAI_MODEL` | no | defaults to `gpt-4o-mini` (needs image input for photo questions) |
| `DATA_GOV_API_KEY` | no | live Agmarknet prices; otherwise sample prices are used and labelled as such |

### Tests

```bash
cd backend
..\.venv\Scripts\python -m pytest
```

Tests use a temporary SQLite database by default. Set `TEST_DATABASE_URL` to run them against a Postgres test database. External APIs are stubbed.

---

## Project structure

```
frontend/                 plain HTML/CSS/JS, served by FastAPI
  api.js                  fetch wrapper + session helpers
  index.html              login / register
  farm.html               farm profile, crop, Soil Health Card
  dashboard.html          today's decisions, forecast, prices, alerts
  decisions.html          inputs → ranked actions with reasons + feedback
  query.html, query.js    AI assistant (text, photo, voice, read-aloud)
  mandi.html              mandi prices and 14-day trend
  schemes / tutorials / contact   static info pages
backend/
  app/main.py             FastAPI app
  app/models.py           SQLAlchemy models
  app/routers/            auth, farms, decisions (signals, recommendations, feedback, evaluation), market, chat
  app/ingestion/          weather, market, soil, crop_stage
  app/engine/             features, pest_risk, fusion, ranker, explain, knowledge/*.yaml
  app/llm.py              OpenAI wrapper
  alembic/                migrations
  seed/mandi_sample.csv   sample price series
  tests/
```

## API overview

| Method & path | Purpose |
|---|---|
| `POST /api/auth/register`, `POST /api/auth/login`, `GET/PUT /api/me`, `GET /api/me/stats` | accounts |
| `GET/POST /api/farms`, `GET/PUT /api/farms/{id}` | farms |
| `POST /api/farms/{id}/crop-cycles`, `POST /api/farms/{id}/soil` | crop and soil data |
| `GET /api/farms/{id}/signals` | the five signal summaries + 7-day forecast |
| `GET /api/farms/{id}/recommendations?refresh=true` | run the engine / get ranked actions |
| `POST /api/recommendations/{id}/feedback` | accept, reject, done (+ outcome, rating) |
| `GET /api/evaluation/summary` | acceptance metrics per rule |
| `GET /api/market/options`, `GET /api/market/prices?state=&commodity=` | mandi prices + trend |
| `POST /api/chat`, `GET /api/chat/history` | AI assistant |

Interactive docs: http://localhost:8000/docs

## Roadmap (from the deck)

- **Phase 2**: satellite imagery (Sentinel/Landsat NDVI crop health) and a trained pest/disease model. The `PestRiskModel` protocol in `engine/pest_risk.py` is the swap-in point.
- **Phase 3**: personalised farm models, more regional languages, a fuller voice interface.
- **Phase 4**: real-world pilots, expert validation of rules and thresholds, continuous feedback.

Current limitations: rule thresholds and crop calendars are generic and illustrative; soil moisture is modelled, not measured; sample mandi prices are synthetic.

## Team

Bheeshma Nair · Parth Vinod Pungle · Shaik Abdul Ashraf · Shreya Basker

This project is intended for educational and hackathon purposes.
