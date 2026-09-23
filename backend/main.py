"""Yale SOM course explorer API desk.

Run from backend/:  uvicorn main:app --reload --port 8000
Open API docs:      http://127.0.0.1:8000/docs
Frontend (Vite):    http://127.0.0.1:5173
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import load_env, run_agent

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_PATH = ROOT / "data" / "yale_som_classes.json"
DIST_PATH = ROOT / "frontend" / "dist"

# agent.load_env walks up from the lecture folder, so a shared .env in a parent
# (e.g. "AI foundations/.env") is picked up as well as a local one.
load_env()

# /api/chat spends real Portkey credits, so a deployed instance is gated behind
# a shared password. Unset (the local-dev default) leaves the endpoint open.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()


def require_password(x_app_password: str = Header(default="")) -> None:
    if not APP_PASSWORD:
        return
    # compare_digest keeps the check constant-time, so the response latency
    # does not leak how much of the password was correct.
    if not secrets.compare_digest(x_app_password, APP_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid or missing password.")


app = FastAPI(title="Yale SOM Courses", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_courses() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)


@app.get("/api/health")
def health():
    return {"ok": True, "courses_file": str(DATA_PATH.name)}


@app.get("/api/config")
def config():
    """Lets the UI know whether to ask the visitor for a password."""
    return {"password_required": bool(APP_PASSWORD)}


@app.get("/api/courses")
def list_courses(q: str | None = Query(default=None)):
    """Return courses for the React catalog (optional text filter)."""
    courses = load_courses()
    if not q:
        return {"count": len(courses), "courses": courses}
    needle = q.lower().strip()
    matched = [
        c
        for c in courses
        if needle in json.dumps(c, ensure_ascii=False).lower()
    ]
    return {"count": len(matched), "courses": matched}


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_password)])
def chat(body: ChatRequest):
    result = run_agent(body.message)
    return ChatResponse(
        reply=result.get("reply", ""),
        tools_used=list(result.get("tools_used") or []),
    )


# The built React app is served from this same origin in production, so the
# frontend can call /api/* with relative URLs. Mounted last so it never shadows
# an /api route. Absent in local dev (no `npm run build`), which is fine —
# Vite serves the UI on :5173 then.
if DIST_PATH.is_dir():
    app.mount("/", StaticFiles(directory=DIST_PATH, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("main:app", host=host, port=port, reload=False)
