"""Generate answer templates for all questions in the bank.

Runs concurrently (10 at a time), saves progress after every batch,
validates the final JSON before writing.

Usage:
    python3 gen_templates.py
    python3 gen_templates.py --resume   # skip already-processed IDs
"""
import asyncio, json, sys, time, argparse
from pathlib import Path
import anthropic
from dotenv import load_dotenv
from question_bank import get_all_questions

load_dotenv('../.env', override=True)

OUT_PATH  = Path('../research/answer_templates.json')
CONCURRENCY = 10

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
                        'label':      {'type': 'string'},
                        'detail':     {'type': 'string'},
                        'importance': {'type': 'integer', 'enum': [1, 2, 3]},
                        'probe':      {'type': 'string'},
                    }
                }
            }
        }
    }
}

PROBE_RULES = """
PROBE QUESTION RULES — match the probe style to the question type:

- DESCRIPTIVE ("typical day", "how do you prepare", "what makes a good X"):
  Stay descriptive. Ask the candidate to elaborate on the missing topic.
  Good: "Walk me through what you actually cover in a crew briefing."
  Bad:  "Tell me about a time you had a conflict during a briefing." ← wrong type

- BEHAVIORAL / TMAAT ("tell me about a time"):
  Dig into the story. Target the missing STAR element.
  Good: "What specifically did you say to the captain in that moment?"
  Good: "How did that situation ultimately resolve?"

- WWYD / CRM SCENARIO ("what would you do if"):
  Walk through the next step in the decision sequence.
  Good: "And if the captain still refused — what then?"

- TECHNICAL:
  Ask for deeper explanation of the missing concept.
  Good: "Can you explain what's actually happening aerodynamically there?"

- PERSONAL / MOTIVATIONAL:
  Ask for a concrete example or more specific detail.
  Good: "Can you give me a specific example of that from your flying career?"

Never change the question type in a probe. Stay on topic.
"""

SYSTEM = (
    "You are an expert airline pilot interview coach. "
    "Given an interview question and its guidance, produce a structured answer template "
    "of 4-8 topics a candidate should cover. "
    "Each topic needs: a short label (3-6 words), a one-sentence detail of what counts "
    "as covering it, an importance rating, and a natural follow-up probe question.\n\n"
    + PROBE_RULES
)

def build_prompt(q: dict) -> str:
    kp = '\n'.join(f'- {p}' for p in q['key_points'])
    return (
        f"Category: {q['category_label']}\n"
        f"Question type: {q['category']}\n"
        f"Question: {q['question']}\n\n"
        f"Expected answer guidance: {q['expected']}\n\n"
        f"Key points:\n{kp}\n\n"
        f"Pitfalls to avoid: {q['avoid']}"
    )

async def generate_one(client: anthropic.AsyncAnthropic, q: dict, sem: asyncio.Semaphore, retries=3) -> dict:
    async with sem:
        for attempt in range(retries):
            try:
                resp = await client.messages.create(
                    model='claude-haiku-4-5',
                    max_tokens=800,
                    system=SYSTEM,
                    messages=[{'role': 'user', 'content': build_prompt(q)}],
                    tools=[TOOL],
                    tool_choice={'type': 'tool', 'name': 'answer_template'},
                )
                tmpl = next(b.input for b in resp.content if b.type == 'tool_use')
                return {
                    'id':             q['id'],
                    'category':       q['category'],
                    'category_label': q['category_label'],
                    'question':       q['question'],
                    'topics':         tmpl['topics'],
                }
            except Exception as e:
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    print(f"  [retry {attempt+1}] id={q['id']} — {e} — waiting {wait}s")
                    await asyncio.sleep(wait)
                else:
                    print(f"  [FAILED] id={q['id']} — {e}")
                    return {'id': q['id'], 'question': q['question'], 'error': str(e), 'topics': []}

async def main(resume: bool):
    questions = get_all_questions()

    # Load existing results if resuming
    existing: dict[int, dict] = {}
    if resume and OUT_PATH.exists():
        with open(OUT_PATH, encoding='utf-8') as f:
            for entry in json.load(f):
                if not entry.get('error'):   # re-process failed entries
                    existing[entry['id']] = entry
        print(f"Resuming — {len(existing)} already done")

    todo = [q for q in questions if q['id'] not in existing]
    total = len(questions)
    print(f"Generating templates for {len(todo)}/{total} questions...")

    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(CONCURRENCY)

    results = list(existing.values())
    done = len(existing)
    t0 = time.time()

    # Process in batches of 20 so we save progress regularly
    BATCH = 20
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        batch_results = await asyncio.gather(*[generate_one(client, q, sem) for q in batch])
        results.extend(batch_results)
        done += len(batch)

        # Save after every batch
        results_sorted = sorted(results, key=lambda x: x['id'])
        tmp = OUT_PATH.with_suffix('.tmp')
        tmp.write_text(json.dumps(results_sorted, indent=2, ensure_ascii=False), encoding='utf-8')
        tmp.replace(OUT_PATH)

        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"  {done}/{total}  ({rate:.1f}/s)  ETA {eta:.0f}s")

    # Final validation
    print("\nValidating JSON...")
    raw = OUT_PATH.read_text(encoding='utf-8')
    parsed = json.loads(raw)          # will raise if invalid
    errors = [e for e in parsed if e.get('error')]
    print(f"Total entries : {len(parsed)}")
    print(f"Errors        : {len(errors)}")
    if errors:
        print("Failed IDs:", [e['id'] for e in errors])
    else:
        print("All valid ✓")

    print(f"Saved to {OUT_PATH.resolve()}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true', help='Skip already-processed IDs')
    args = parser.parse_args()
    asyncio.run(main(args.resume))
