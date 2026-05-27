"""Generate answer templates for 3 random questions, save as structured JSON."""
import json, random, sys
import anthropic
from dotenv import load_dotenv
from question_bank import get_all_questions

load_dotenv('../.env', override=True)
client = anthropic.Anthropic()

TOOL = {
    'name': 'answer_template',
    'description': 'Structured answer template for an interview question.',
    'strict': True,
    'input_schema': {
        'type': 'object',
        'additionalProperties': False,
        'required': ['topics'],
        'properties': {
            'topics': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['label', 'detail', 'importance', 'probe'],
                    'properties': {
                        'label':      {'type': 'string', 'description': '3-6 word topic name'},
                        'detail':     {'type': 'string', 'description': 'One sentence: what specifically counts as covering this topic'},
                        'importance': {'type': 'integer', 'enum': [1, 2, 3],
                                       'description': '1=required (missing=weak), 2=important (all covered=strong), 3=bonus'},
                        'probe':      {'type': 'string', 'description': 'Follow-up question if this topic is not covered — see probe rules'},
                    }
                }
            }
        }
    }
}

PROBE_RULES = """
PROBE QUESTION RULES — match the probe style to the question type:

- DESCRIPTIVE questions ("typical day", "how do you prepare", "what makes a good X"):
  Probes must stay descriptive. Ask the candidate to elaborate on the missing topic.
  Good: "Walk me through what you actually cover in a crew briefing."
  Bad:  "Tell me about a time you had a conflict during a briefing." ← wrong type

- BEHAVIORAL / TMAAT questions ("tell me about a time"):
  Probes dig into the story. Target the missing STAR element.
  Good: "What specifically did you say to the captain in that moment?"
  Good: "How did that situation ultimately resolve?"
  Bad:  "Why is CRM important?" ← too generic

- WWYD / CRM SCENARIO questions ("what would you do if"):
  Probes walk through the next step in the decision sequence.
  Good: "And if the captain still refused to climb — what then?"
  Good: "Who else would you involve at that point?"

- TECHNICAL questions:
  Probes ask for deeper explanation of the missing concept.
  Good: "Can you explain what's actually happening aerodynamically there?"
  Good: "How would that change at higher altitude or heavier weight?"

- PERSONAL / MOTIVATIONAL questions:
  Probes ask for a concrete example or more specific detail.
  Good: "Can you give me a specific example of that from your flying career?"
  Bad:  "Why do you want to be a pilot?" ← different question entirely

Never change the question type in a probe. Stay on topic.
"""

SYSTEM = (
    "You are an expert airline pilot interview coach. "
    "Given an interview question and its guidance, produce a structured answer template "
    "of 4-8 topics a candidate should cover. "
    "Each topic needs: a short label, a one-sentence detail of what counts as covering it, "
    "an importance rating, and a natural follow-up probe question.\n\n"
    + PROBE_RULES
)

def build_prompt(q):
    kp = '\n'.join(f'- {p}' for p in q['key_points'])
    return (
        f"Category: {q['category_label']}\n"
        f"Question type: {q['category']}\n"
        f"Question: {q['question']}\n\n"
        f"Expected answer guidance: {q['expected']}\n\n"
        f"Key points from research:\n{kp}\n\n"
        f"Pitfalls to avoid: {q['avoid']}"
    )

def generate(q):
    resp = client.messages.create(
        model='claude-haiku-4-5',
        max_tokens=800,
        system=SYSTEM,
        messages=[{'role': 'user', 'content': build_prompt(q)}],
        tools=[TOOL],
        tool_choice={'type': 'tool', 'name': 'answer_template'},
    )
    return next(b.input for b in resp.content if b.type == 'tool_use')

# ── Run ───────────────────────────────────────────────────────────────────────
questions = get_all_questions()
sample = random.sample(questions, 3)

results = []
for q in sample:
    tmpl = generate(q)
    entry = {
        'id':             q['id'],
        'category':       q['category'],
        'category_label': q['category_label'],
        'question':       q['question'],
        'topics':         tmpl['topics'],
    }
    results.append(entry)

# Save structured JSON
out_path = '../research/answer_templates_sample.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Print human-readable summary
for entry in results:
    print(f"\n{'='*68}")
    print(f"id: {entry['id']}  [{entry['category_label']}]")
    print(f"Q: {entry['question']}\n")
    for t in entry['topics']:
        imp = {1: '★★★ required', 2: '★★☆ important', 3: '★☆☆ bonus'}[t['importance']]
        print(f"  {imp}  {t['label']}")
        print(f"    {t['detail']}")
        print(f'    → "{t["probe"]}"')

print(f"\n\nSaved to {out_path}")
