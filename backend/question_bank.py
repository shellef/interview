"""Parse and serve questions from the question bank file."""
import json
import os
import random
import re
from functools import lru_cache
from pathlib import Path

BANK_PATH = Path(__file__).parent.parent / "research" / "question_bank.txt"

CATEGORIES = {
    "personal":     "Personal / Motivational",
    "behavioral":   "Competency / Behavioral — TMAAT",
    "crm":          "CRM / Scenario / WWYD",
    "regulations":  "Technical — Regulations & Airspace",
    "aerodynamics": "Technical — Aerodynamics & Performance",
    "systems":      "Technical — Systems & Aircraft",
    "meteorology":  "Technical — Meteorology & Navigation",
    "company":      "Company-Specific",
    "career":       "Professionalism & Career",
}

CATEGORY_SLUGS = {v.upper(): k for k, v in CATEGORIES.items()}


def _parse_bank(path: Path) -> list[dict]:
    """Parse question_bank.txt into a list of question dicts."""
    lines = path.read_text(encoding="utf-8").splitlines()
    questions = []
    current_section = "unknown"
    q_id = 0

    entry: dict | None = None
    mode: str | None = None

    def flush():
        nonlocal entry
        if entry and entry["question"]:
            questions.append(entry)
        entry = None

    for line in lines:
        # Section header: "SECTION N: Name (N questions)"
        m = re.match(r"SECTION \d+:\s*(.+?)\s*\(\d+", line)
        if m:
            flush()
            header = m.group(1).strip()
            current_section = CATEGORY_SLUGS.get(header.upper(), "unknown")
            mode = None
            continue

        # New question
        if line.startswith("Q:"):
            flush()
            entry = {
                "id": q_id,
                "category": current_section,
                "category_label": CATEGORIES.get(current_section, current_section),
                "question": line[2:].strip(),
                "expected": "",
                "key_points": [],
                "avoid": "",
            }
            q_id += 1
            mode = None
            continue

        if entry is None:
            continue

        if line.startswith("EXPECTED:"):
            entry["expected"] = line[9:].strip()
            mode = "expected"
        elif line.startswith("KEY POINTS:"):
            mode = "key_points"
        elif line.startswith("AVOID:"):
            entry["avoid"] = line[6:].strip()
            mode = "avoid"
        elif mode == "expected" and line.strip():
            entry["expected"] += " " + line.strip()
        elif mode == "key_points" and line.strip().startswith("-"):
            entry["key_points"].append(line.strip().lstrip("- ").strip())
        elif mode == "avoid" and line.strip() and not line.startswith("="):
            if mode == "avoid":
                entry["avoid"] += " " + line.strip()

    flush()
    return questions


# Questions removed from the active pool (pure factual trivia, not interview questions)
_SKIP_IDS: set[int] = {
    190,   # How many aircraft do we operate and what are our main bases?
    192,   # Who are the CEO, Director of Flight Operations, and Chief Pilot?
    193,   # What is our financial performance — revenue, passengers carried, growth?
    202,   # What are Southwest's three core values? (memorisation, not insight)
    204,   # What new aircraft do we have on order?
}


@lru_cache(maxsize=1)
def get_all_questions() -> list[dict]:
    return [q for q in _parse_bank(BANK_PATH) if q["id"] not in _SKIP_IDS]


def get_random_question(category: str | None = None) -> dict:
    questions = get_all_questions()
    if category and category in CATEGORIES:
        pool = [q for q in questions if q["category"] == category]
        if not pool:
            pool = questions
    else:
        pool = questions
    return random.choice(pool)


def get_question_by_id(q_id: int) -> dict | None:
    questions = get_all_questions()
    for q in questions:
        if q["id"] == q_id:
            return q
    return None


# ── Answer templates ──────────────────────────────────────────────────────────

TEMPLATES_PATH = Path(__file__).parent.parent / "research" / "answer_templates.json"


@lru_cache(maxsize=1)
def get_all_templates() -> dict[int, dict]:
    """Return {question_id: template_entry}."""
    if not TEMPLATES_PATH.exists():
        return {}
    data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in data}


def get_template(q_id: int) -> dict | None:
    return get_all_templates().get(q_id)
