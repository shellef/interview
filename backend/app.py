"""FastAPI backend for the AI Interview system."""
import json
import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api as lkapi
from pydantic import BaseModel

from interview import InterviewSession

app = FastAPI(title="AI Interview")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store
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
def start_interview(req: StartRequest) -> SessionResponse:
    """Create a session and run the full interview synchronously."""
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
def get_session(session_id: str) -> SessionResponse:
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
def next_turn(session_id: str) -> SessionResponse:
    """Run one more exchange on an existing session."""
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
async def get_voice_token(req: VoiceTokenRequest) -> dict:
    """Create a LiveKit room with role metadata and return a join token."""
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
def judge_session(session_id: str) -> SessionResponse:
    """Run the judge on the current transcript."""
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
