import os
import anthropic
from dotenv import load_dotenv

# Walk up from this file to find .env
_here = os.path.abspath(os.path.dirname(__file__))
for _candidate in [_here, os.path.dirname(_here)]:
    _env = os.path.join(_candidate, ".env")
    if os.path.exists(_env):
        load_dotenv(_env, override=True)
        break

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

INTERVIEWER_MODEL = "claude-opus-4-7"
INTERVIEWEE_MODEL = "claude-haiku-4-5"
JUDGE_MODEL = "claude-opus-4-7"


def _load_prompt(name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", f"{name}.txt")
    with open(path) as f:
        return f.read().strip()


def interviewer_turn(role: str, history: list[dict]) -> str:
    """
    Given the job role and conversation history (question/answer pairs),
    generate the interviewer's next question.
    history format: [{"role": "user"|"assistant", "content": str}, ...]
    From the interviewer's perspective: assistant=interviewer, user=candidate
    """
    system = _load_prompt("interviewer") + f"\n\nThe role being interviewed for: {role}"

    messages = history if history else [
        {"role": "user", "content": "Please begin the interview."}
    ]

    response = client.messages.create(
        model=INTERVIEWER_MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def interviewee_turn(role: str, history: list[dict]) -> str:
    """
    Given the job role and conversation history, generate the candidate's answer.
    history format: [{"role": "user"|"assistant", "content": str}, ...]
    From the interviewee's perspective: user=interviewer question, assistant=candidate answer
    """
    system = _load_prompt("interviewee") + f"\n\nThe role you are interviewing for: {role}"

    response = client.messages.create(
        model=INTERVIEWEE_MODEL,
        max_tokens=1024,
        system=system,
        messages=history,
    )
    return response.content[0].text


def judge_interview(transcript: str) -> dict:
    """
    Given the full interview transcript as a string, return a structured verdict.
    """
    import json

    system = _load_prompt("judge")

    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": f"Interview transcript:\n\n{transcript}"}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
