"""
Interview session management.

Maintains two separate message histories:
  - interviewer_history: from the interviewer's POV (assistant=interviewer, user=candidate)
  - interviewee_history: from the interviewee's POV (user=interviewer, assistant=candidate)

This enforces zero knowledge sharing between the two agents.
"""
from dataclasses import dataclass, field
from agents import interviewer_turn, interviewee_turn, judge_interview


@dataclass
class Turn:
    speaker: str  # "interviewer" | "interviewee"
    text: str


@dataclass
class InterviewSession:
    role: str
    turns: list[Turn] = field(default_factory=list)
    verdict: dict | None = None

    # Separate isolated histories for each agent
    _interviewer_history: list[dict] = field(default_factory=list)
    _interviewee_history: list[dict] = field(default_factory=list)

    def run_turn(self) -> tuple[str, str]:
        """
        Run one full exchange: interviewer asks, interviewee answers.
        Returns (question, answer).
        """
        question = interviewer_turn(self.role, self._interviewer_history)
        self.turns.append(Turn("interviewer", question))

        # Update each history independently
        self._interviewer_history.append({"role": "assistant", "content": question})
        self._interviewee_history.append({"role": "user", "content": question})

        answer = interviewee_turn(self.role, self._interviewee_history)
        self.turns.append(Turn("interviewee", answer))

        self._interviewer_history.append({"role": "user", "content": answer})
        self._interviewee_history.append({"role": "assistant", "content": answer})

        return question, answer

    def run(self, num_turns: int = 3) -> dict:
        """Run the full interview for `num_turns` exchanges, then judge."""
        for _ in range(num_turns):
            self.run_turn()

        self.verdict = judge_interview(self.transcript())
        return self.verdict

    def transcript(self) -> str:
        lines = []
        for turn in self.turns:
            label = "Interviewer" if turn.speaker == "interviewer" else "Candidate"
            lines.append(f"{label}: {turn.text}")
        return "\n\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "turns": [{"speaker": t.speaker, "text": t.text} for t in self.turns],
            "verdict": self.verdict,
        }
