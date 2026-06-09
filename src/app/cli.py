from __future__ import annotations

import argparse

from app.graph import ShoppingAssistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Student scaffold CLI.")
    parser.add_argument("--question", help="Run one question through the graph.")
    parser.add_argument("--test-file", default="data/test.json")
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--batch", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    assistant = ShoppingAssistant()

    if args.batch:
        from pathlib import Path
        test_file = Path(args.test_file)
        output_dir = Path("output")
        result = assistant.run_batch(test_file=test_file, output_dir=output_dir)
        print(f"Batch completed: {result['total']} questions processed. Summary saved to {result['summary_file']}.")
    elif args.question:
        from pathlib import Path
        trace_file = Path(args.trace_file) if args.trace_file else None
        result = assistant.ask(args.question, trace_file=trace_file)
        print("\n=== FINAL ANSWER ===\n")
        print(result.get("final_answer", ""))
    else:
        print("Please provide --question or --batch.")


if __name__ == "__main__":
    main()
