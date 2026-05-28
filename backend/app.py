"""FastAPI backend for the AI Interview system."""
import asyncio
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = anthropic.Anthropic()

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
REQUIRE_AUTH   = os.environ.get("REQUIRE_AUTH", "true").lower() not in ("false", "0", "no")


def _google_redirect_uri() -> str:
    return f"{EXTERNAL_URL}/login/google/callback"


def login_required(request: Request):
    if not REQUIRE_AUTH:
        return
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
    if REQUIRE_AUTH and "user" not in request.session:
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


# ---------------------------------------------------------------------------
# Practice mode — single question building block
# ---------------------------------------------------------------------------

from question_bank import CATEGORIES, get_all_questions, get_question_by_id, get_random_question, get_template


class QuestionResponse(BaseModel):
    id: int
    category: str
    category_label: str
    question: str


class EvaluateRequest(BaseModel):
    question_id: int
    answer: str


class EvaluateResponse(BaseModel):
    score: str          # "strong" | "adequate" | "weak"
    summary: str        # 1-2 sentence overall assessment
    covered: list[str]  # key points the answer covered
    missed: list[str]   # key points missing
    advice: str         # one concrete improvement tip


MAX_FOLLOWUPS = 3   # max probe rounds before forcing evaluation


class Turn(BaseModel):
    role: str     # "interviewer" | "candidate"
    content: str


class TurnRequest(BaseModel):
    question_id: int
    turns: list[Turn]   # full conversation so far (not including initial question)


class TurnResponse(BaseModel):
    action: str                  # "probe" | "done"
    probe: str | None = None     # next question to ask (action=probe)
    topic: str | None = None     # which topic the probe targets
    result: EvaluateResponse | None = None  # filled when action=done


@app.post("/practice/turn")
def practice_turn(req: TurnRequest, _=Depends(login_required)) -> TurnResponse:
    q = get_question_by_id(req.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    tmpl = get_template(req.question_id)
    topics = tmpl["topics"] if tmpl else []


    # Count candidate turns so far
    candidate_turns = [t for t in req.turns if t.role == "candidate"]
    force_done = len(candidate_turns) >= MAX_FOLLOWUPS + 1  # initial + follow-ups

    # Build conversation string for the prompt
    convo = "\n".join(
        f"{'Interviewer' if t.role == 'interviewer' else 'Candidate'}: {t.content}"
        for t in req.turns
    )

    topics_list = "\n".join(
        f"- [{['required','important','bonus'][t['importance']-1].upper()}] {t['label']}: {t['detail']}"
        for t in topics
    )

    system = "You are assessing coverage of interview topics. Be strict: a topic is only covered if the candidate explicitly addressed it."

    # Numbered topic list for Claude to reference by index
    numbered_topics = "\n".join(
        f"{i}. [{['REQUIRED','IMPORTANT','BONUS'][t['importance']-1]}] {t['label']}: {t['detail']}"
        for i, t in enumerate(topics)
    )

    if force_done:
        prompt = f"""Interview question: {q['question']}

Expected topics:
{numbered_topics}

Conversation so far:
{convo}

Evaluate the candidate's performance across the full conversation."""
        tool_choice = {"type": "tool", "name": "evaluate"}
    else:
        prompt = f"""Interview question: {q['question']}

Expected topics (numbered):
{numbered_topics}

Conversation so far:
{convo}

Which REQUIRED or IMPORTANT topics have NOT been addressed by the candidate?
- If any are missing, return the index of the single most important uncovered topic.
- If all REQUIRED and IMPORTANT topics are covered, evaluate instead.
- Never select a BONUS topic."""
        tool_choice = {"type": "any"}

    tools = [
        {
            "name": "probe_topic",
            "description": "Ask a natural follow-up question targeting one specific uncovered topic.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic_index", "probe"],
                "properties": {
                    "topic_index": {
                        "type": "integer",
                        "description": "0-based index of the uncovered topic",
                    },
                    "probe": {
                        "type": "string",
                        "description": (
                            "One short, natural follow-up question for that topic. "
                            "Sound like a real interviewer. Do not mention topics outside the list."
                        ),
                    },
                },
            },
        },
        {
            "name": "evaluate",
            "description": "All key topics are covered — give the final evaluation.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["score", "summary", "covered", "missed", "advice"],
                "properties": {
                    "score":   {"type": "string", "enum": ["strong", "adequate", "weak"]},
                    "summary": {"type": "string"},
                    "covered": {"type": "array", "items": {"type": "string"}},
                    "missed":  {"type": "array", "items": {"type": "string"}},
                    "advice":  {"type": "string"},
                },
            },
        },
    ]

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=tools,
        tool_choice=tool_choice,
    )

    for block in response.content:
        if block.type == "tool_use":
            if block.name == "probe_topic":
                idx = block.input["topic_index"]
                probe_text = block.input.get("probe", "")
                if 0 <= idx < len(topics) and probe_text:
                    return TurnResponse(action="probe", probe=probe_text, topic=topics[idx]["label"])
            if block.name == "evaluate":
                return TurnResponse(action="done", result=EvaluateResponse(**block.input))

    raise HTTPException(status_code=500, detail="No tool call returned")


class StudyQuestion(BaseModel):
    id: int
    category: str
    category_label: str
    question: str
    topics: list[dict]


@app.get("/practice/study-question")
def study_question(category: str | None = None, _=Depends(login_required)) -> StudyQuestion:
    q   = get_random_question(category)
    tmpl = get_template(q["id"])
    return StudyQuestion(
        id=q["id"], category=q["category"], category_label=q["category_label"],
        question=q["question"],
        topics=tmpl["topics"] if tmpl else [],
    )


@app.get("/practice/cheatsheet")
def question_cheatsheet(question_id: int, topic: str | None = None, _=Depends(login_required)):
    """
    Initial question: return a sample answer covering all key points.
    Follow-up: return the focused topic label + a short answer for just that topic.
    """
    q    = get_question_by_id(question_id)
    tmpl = get_template(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    if topic:
        # Follow-up mode: answer only the specific topic being probed
        topic_detail = next(
            (t["detail"] for t in (tmpl["topics"] if tmpl else []) if t["label"] == topic),
            topic,
        )
        content = (
            f"Interview question: {q['question']}\n"
            f"Follow-up topic: {topic}\n"
            f"What this means: {topic_detail}"
        )
    else:
        # Initial question mode: cover all required/important topics
        key_points = "\n".join(
            f"- {t['label']}: {t['detail']}"
            for t in (tmpl["topics"] if tmpl else [])
            if t["importance"] in (1, 2)
        )
        content = f"Interview question: {q['question']}\n\nKey points to cover:\n{key_points}"

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=120,
        system=(
            "You are an experienced airline pilot in a job interview. "
            "Give a concise, natural answer — 2 sentences maximum. "
            "Be specific. Sound like a pilot speaking, not a textbook."
        ),
        messages=[{"role": "user", "content": content}],
    )

    return {
        "id":             q["id"],
        "category_label": q["category_label"],
        "question":       q["question"],
        "topic":          topic,          # None for initial, label string for follow-ups
        "answer":         response.content[0].text,
    }


@app.get("/practice/template")
def question_template(question_id: int, _=Depends(login_required)):
    q    = get_question_by_id(question_id)
    tmpl = get_template(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return {
        "id":             q["id"],
        "category_label": q["category_label"],
        "question":       q["question"],
        "topics":         tmpl["topics"] if tmpl else [],
    }


@app.get("/practice/question")
def practice_question(category: str | None = None, _=Depends(login_required)) -> QuestionResponse:
    q = get_random_question(category)
    return QuestionResponse(**{k: q[k] for k in QuestionResponse.model_fields})


@app.get("/practice/categories")
def practice_categories(_=Depends(login_required)) -> dict:
    return {"categories": [{"slug": k, "label": v} for k, v in CATEGORIES.items()]}


@app.post("/practice/evaluate")
def practice_evaluate(req: EvaluateRequest, _=Depends(login_required)) -> EvaluateResponse:
    q = get_question_by_id(req.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")


    system = "You are an expert airline pilot interview coach evaluating a candidate's answer."

    prompt = f"""Question: {q['question']}

Expected guidance: {q['expected']}

Key points a strong answer covers:
{chr(10).join(f'- {p}' for p in q['key_points'])}

Common mistakes: {q['avoid']}

Candidate's answer: {req.answer}"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[{
            "name": "evaluate_answer",
            "description": "Submit the structured evaluation of the candidate's answer.",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "score":   {"type": "string", "enum": ["strong", "adequate", "weak"]},
                    "summary": {"type": "string", "description": "1-2 sentence overall assessment"},
                    "covered": {"type": "array",  "items": {"type": "string"}, "description": "Key points the candidate covered"},
                    "missed":  {"type": "array",  "items": {"type": "string"}, "description": "Key points missing or underdeveloped"},
                    "advice":  {"type": "string", "description": "One concrete improvement tip"},
                },
                "required": ["score", "summary", "covered", "missed", "advice"],
                "additionalProperties": False,
            },
        }],
        tool_choice={"type": "tool", "name": "evaluate_answer"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return EvaluateResponse(**block.input)

    raise HTTPException(status_code=500, detail="Evaluation produced no result")


class SpeakRequest(BaseModel):
    text: str


from fastapi import File, UploadFile


@app.post("/practice/transcribe")
async def practice_transcribe(audio: UploadFile = File(...), _=Depends(login_required)):
    """Send recorded audio to Deepgram nova-3 and return the transcript."""
    import urllib.request as urlreq

    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key:
        raise HTTPException(status_code=500, detail="DEEPGRAM_API_KEY not set")

    audio_bytes = await audio.read()
    content_type = audio.content_type or "audio/webm"

    def _transcribe():
        r = urlreq.Request(
            "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&language=en",
            data=audio_bytes,
            headers={
                "Authorization": f"Token {key}",
                "Content-Type": content_type,
            },
            method="POST",
        )
        with urlreq.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read())

    result = await asyncio.to_thread(_transcribe)
    try:
        transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        transcript = ""
    return {"transcript": transcript}


@app.post("/practice/speak")
async def practice_speak(req: SpeakRequest, _=Depends(login_required)):
    """Proxy text to Deepgram TTS and return audio bytes."""
    import urllib.request as urlreq

    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key:
        raise HTTPException(status_code=500, detail="DEEPGRAM_API_KEY not set")

    def _fetch():
        data = json.dumps({"text": req.text}).encode()
        r = urlreq.Request(
            "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=mp3",
            data=data,
            headers={
                "Authorization": f"Token {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlreq.urlopen(r, timeout=15) as resp:
            return resp.read()

    from fastapi.responses import Response as FResponse
    audio = await asyncio.to_thread(_fetch)
    return FResponse(content=audio, media_type="audio/mpeg")


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
