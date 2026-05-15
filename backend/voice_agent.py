"""LiveKit voice agent — structured airline pilot interview with hardcoded questions."""
import asyncio

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import deepgram, openai, silero

load_dotenv()

_CEREBRAS_MODEL = "gpt-oss-120b"

GREETING = (
    "Good morning. I'm Sarah, a recruiter with the airline's hiring team. "
    "Welcome to your interview. I'll be asking you three questions today. Let's begin."
)

QUESTIONS = [
    "Tell me about yourself and why you want to be an airline pilot. "
    "Walk me through your journey in aviation and what shaped your decision to pursue this career.",

    "Tell me about a time when you had a conflict or disagreement in the flight deck "
    "with a crew member, and how you resolved it.",

    "Describe a specific time when you had to make a difficult decision during a flight. "
    "Walk me through what was at stake, what you considered, and how you ensured safety "
    "was the primary factor in your decision.",
]

ACKNOWLEDGMENTS = ["Thank you.", "I appreciate you sharing that."]

CLOSING = (
    "Thank you for your time today. That concludes your interview. "
    "We'll be in touch soon. Best of luck to you."
)


class InterviewerAgent(Agent):
    def __init__(self, ctx: JobContext) -> None:
        super().__init__(instructions="")
        self._idx = 0
        self._ctx = ctx

    async def on_enter(self) -> None:
        await self.session.say(f"{GREETING} {QUESTIONS[0]}", allow_interruptions=False)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        if self._idx < len(QUESTIONS) - 1:
            ack = ACKNOWLEDGMENTS[self._idx % len(ACKNOWLEDGMENTS)]
            self._idx += 1
            await self.session.say(f"{ack} {QUESTIONS[self._idx]}", allow_interruptions=False)
        else:
            await self.session.say(CLOSING, allow_interruptions=False)
            await asyncio.sleep(1)
            await self._ctx.room.local_participant.publish_data(b"interview_complete")

    async def llm_node(self, chat_ctx, tools, model_settings):
        # All speech is hardcoded — block the LLM pipeline entirely
        return
        yield  # makes this an async generator


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    session = AgentSession(
        vad=silero.VAD.load(min_silence_duration=0.8),
        stt=deepgram.STT(model="nova-3"),
        llm=openai.LLM.with_cerebras(model=_CEREBRAS_MODEL),
        tts=deepgram.TTS(model="aura-2-thalia-en"),
        allow_interruptions=False,
        min_endpointing_delay=1.5,
    )

    await session.start(agent=InterviewerAgent(ctx=ctx), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
