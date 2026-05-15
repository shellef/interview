#!/usr/bin/env python3
"""Simple CLI to run an interview end-to-end."""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from interview import InterviewSession


def main():
    parser = argparse.ArgumentParser(description="Run an AI-to-AI interview")
    parser.add_argument("--role", default="senior backend engineer", help="Job role to interview for")
    parser.add_argument("--turns", type=int, default=3, help="Number of Q&A exchanges")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  AI Interview: {args.role}")
    print(f"  {args.turns} exchange(s)")
    print(f"{'='*60}\n")

    session = InterviewSession(role=args.role)

    for i in range(args.turns):
        print(f"--- Turn {i+1} ---")
        question, answer = session.run_turn()
        print(f"\nInterviewer: {question}")
        print(f"\nCandidate:   {answer}")
        print()

    print(f"{'='*60}")
    print("Running judge...")
    print(f"{'='*60}\n")

    from agents import judge_interview
    verdict = judge_interview(session.transcript())
    session.verdict = verdict

    print(f"Level:      {verdict['level'].upper()}  (confidence: {verdict['confidence']})")
    print(f"\nSummary:\n{verdict['summary']}")

    if verdict.get("signals", {}).get("positive"):
        print("\nPositive signals:")
        for s in verdict["signals"]["positive"]:
            print(f"  + {s}")

    if verdict.get("signals", {}).get("negative"):
        print("\nConcerns:")
        for s in verdict["signals"]["negative"]:
            print(f"  - {s}")

    if verdict.get("recommended_follow_ups"):
        print("\nRecommended follow-ups:")
        for s in verdict["recommended_follow_ups"]:
            print(f"  ? {s}")

    print()


if __name__ == "__main__":
    main()
