# Yale SOM Course Explorer

A course catalog browser for Yale SOM with an AI assistant that answers
questions about courses, faculty, and schedules.

- **Backend** — FastAPI, with a [Pydantic AI](https://ai.pydantic.dev) agent
  routed through [Portkey](https://portkey.ai). Tools: catalog search and web
  search.
- **Frontend** — React + TypeScript, built with Vite.
- **Data** — 234 courses, available as both `data/yale_som_classes.json` and
  `data/yale_som.db` (SQLite).

## Running locally

You need Python 3.12+ and Node 22+.

**1. Set your API key.** Copy `.env.example` to `.env` and fill in your Portkey
key:

```bash
cp .env.example .env
```

The backend also walks up parent directories looking for a `.env`, so a shared
one above the repo works too.

**2. Start the backend** (from `backend/`):

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn main:app --reload --port 8000
```

API docs land at http://127.0.0.1:8000/docs.

**3. Start the frontend** (from `frontend/`, in a second terminal):

```bash
npm install && npm run dev
```

Open http://127.0.0.1:5173.

## Deploying

The `Dockerfile` builds the React bundle and serves it from FastAPI, so the
whole app runs as a single service on one URL — `/api/*` is the API, everything
else is the UI.

`render.yaml` configures a free [Render](https://render.com) web service. Set
two environment variables in the Render dashboard (neither is ever committed):

| Variable | Purpose |
| --- | --- |
| `PORTKEY_API_KEY` | Required. Authenticates the agent's model calls. |
| `APP_PASSWORD` | Optional but strongly recommended in public deployments. |

### The password gate

`/api/chat` spends real API credits, so a deployed instance should not be open
to the world. When `APP_PASSWORD` is set, the UI asks visitors for it once and
remembers it in `localStorage`; requests carry it in an `X-App-Password` header.

Leaving `APP_PASSWORD` unset disables the gate entirely — convenient locally,
unwise anywhere public.
