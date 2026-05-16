"""FastAPI backend for the AI Interview system."""
import json
import os
import secrets
import urllib.parse
import urllib.request
import uuid

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from livekit import api as lkapi
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from interview import InterviewSession

app = FastAPI(title="AI Interview")

_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", secrets.token_hex(32)))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---------------------------------------------------------------------------
# Auth configuration
# ---------------------------------------------------------------------------

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
ALLOWED_EMAILS       = {e.strip() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}
EXTERNAL_URL         = os.environ.get("EXTERNAL_URL", "http://localhost:8000").rstrip("/")

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def _google_redirect_uri() -> str:
    return f"{EXTERNAL_URL}/login/google/callback"


def login_required(request: Request):
    if "user" not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Login — AI Interview</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Arial, sans-serif; background: #0f1117;
           display: flex; justify-content: center; align-items: center; min-height: 100vh; }}
    .box {{ background: #1e2433; border-radius: 10px; padding: 40px 36px;
           max-width: 340px; width: 100%; box-shadow: 0 4px 24px rgba(0,0,0,0.4); }}
    h1 {{ font-size: 1.25em; margin-bottom: 28px; text-align: center; color: #f8fafc; }}
    .btn-google {{ display: block; background: #4285F4; color: white;
                  padding: 12px 20px; border-radius: 6px; text-decoration: none;
                  text-align: center; font-size: 0.95em; font-weight: 500; }}
    .btn-google:hover {{ background: #3367D6; }}
    .error {{ color: #fc8181; margin-top: 16px; text-align: center; font-size: 0.9em; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>AI Interview</h1>
    {google_button}
    {error_block}
  </div>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    if "user" in request.session:
        return RedirectResponse("/")
    error = request.session.pop("login_error", None)
    google_button = '<a href="/login/google" class="btn-google">Sign in with Google</a>' if GOOGLE_ENABLED else "<p style='color:#94a3b8;text-align:center'>Google auth not configured.</p>"
    error_block = f'<div class="error">{error}</div>' if error else ""
    return LOGIN_HTML.format(google_button=google_button, error_block=error_block)


@app.get("/login/google")
async def login_google(request: Request):
    if not GOOGLE_ENABLED:
        raise HTTPException(status_code=400, detail="Google auth not configured")
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@app.get("/login/google/callback")
async def login_google_callback(request: Request):
    if request.query_params.get("state") != request.session.pop("oauth_state", None):
        request.session["login_error"] = "Invalid OAuth state. Please try again."
        return RedirectResponse("/login")

    code = request.query_params.get("code")
    if not code:
        request.session["login_error"] = "Google sign-in failed (no code)."
        return RedirectResponse("/login")

    try:
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": _google_redirect_uri(),
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read())
        access_token = token_data["access_token"]

        req = urllib.request.Request(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            userinfo = json.loads(resp.read())
        email = userinfo.get("email", "")
    except Exception as e:
        request.session["login_error"] = f"Google sign-in error: {e}"
        return RedirectResponse("/login")

    if not userinfo.get("email_verified"):
        request.session["login_error"] = "Google account email is not verified."
        return RedirectResponse("/login")

    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        request.session["login_error"] = f"Access denied for {email}."
        return RedirectResponse("/login")

    request.session["user"] = email
    return RedirectResponse("/")


@app.get("/")
async def root(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/login")
    return FileResponse(_DIST / "index.html")


@app.get("/auth/check")
async def auth_check(request: Request):
    if "user" not in request.session:
        raise HTTPException(status_code=401)
    return {"user": request.session["user"]}


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

sessions: dict[str, InterviewSession] = {}


class StartRequest(BaseModel):
    role: str
    num_turns: int = 3


class SessionResponse(BaseModel):
    session_id: str
    role: str
    turns: list[dict]
    verdict: dict | None = None
    done: bool


@app.post("/interview/start")
def start_interview(req: StartRequest, _=Depends(login_required)) -> SessionResponse:
    session_id = str(uuid.uuid4())
    session = InterviewSession(role=req.role)
    sessions[session_id] = session
    session.run(num_turns=req.num_turns)
    return SessionResponse(
        session_id=session_id,
        role=session.role,
        turns=session.to_dict()["turns"],
        verdict=session.verdict,
        done=True,
    )


@app.get("/interview/{session_id}")
def get_session(session_id: str, _=Depends(login_required)) -> SessionResponse:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        session_id=session_id,
        role=session.role,
        turns=session.to_dict()["turns"],
        verdict=session.verdict,
        done=session.verdict is not None,
    )


@app.post("/interview/{session_id}/next")
def next_turn(session_id: str, _=Depends(login_required)) -> SessionResponse:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.run_turn()
    return SessionResponse(
        session_id=session_id,
        role=session.role,
        turns=session.to_dict()["turns"],
        verdict=session.verdict,
        done=False,
    )


class VoiceTokenRequest(BaseModel):
    role: str


@app.post("/voice/token")
async def get_voice_token(req: VoiceTokenRequest, _=Depends(login_required)) -> dict:
    room_name = f"interview-{uuid.uuid4().hex[:8]}"
    lk_url = os.environ["LIVEKIT_URL"]
    api_key = os.environ["LIVEKIT_API_KEY"]
    api_secret = os.environ["LIVEKIT_API_SECRET"]

    async with lkapi.LiveKitAPI(url=lk_url, api_key=api_key, api_secret=api_secret) as lk:
        await lk.room.create_room(
            lkapi.CreateRoomRequest(
                name=room_name,
                metadata=json.dumps({"role": req.role}),
            )
        )

    token = (
        lkapi.AccessToken(api_key, api_secret)
        .with_identity("candidate")
        .with_name("Candidate")
        .with_grants(lkapi.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    return {"token": token, "url": lk_url, "room_name": room_name}


@app.post("/interview/{session_id}/judge")
def judge_session(session_id: str, _=Depends(login_required)) -> SessionResponse:
    from agents import judge_interview

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.verdict = judge_interview(session.transcript())
    return SessionResponse(
        session_id=session_id,
        role=session.role,
        turns=session.to_dict()["turns"],
        verdict=session.verdict,
        done=True,
    )
