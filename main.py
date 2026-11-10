"""Run a supplied evaluation repair and display its public evidence."""

import argparse
import json
import sys

from bootstrap import build_repair_service


def main(argv: list[str] | None = None) -> int:
    """Parse the repair command and return a process exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser("repair", help="Repair a supplied evaluation copy")
    repair.add_argument("project", help="Evaluation path, such as evals/arithmetic")
    repair.add_argument("--provider", choices=["scripted"], default="scripted")
    commands.add_parser("ui", help="Start the local repair interface")
    args = parser.parse_args(argv)

    if args.command == "ui":
        from adapters.gradio_ui import create_demo

        create_demo().launch(server_name="127.0.0.1", share=False)
        return 0

    try:
        result = build_repair_service(args.provider).run(args.project)
    except (ValueError, OSError) as exc:
        print(f"Repair failed: {exc}", file=sys.stderr)
        return 1

    print("Repair trace:")
    for event in result.trace:
        print(json.dumps(event, ensure_ascii=False), flush=True)
    print(f"Workspace: {result.workspace}")
    print("Changed relative files:")
    for path in result.changed_files:
        print(f"  {path}")
    if not result.changed_files:
        print("  (none)")
    print("Final sandboxed test result:")
    if result.last_test is None:
        print("Tests did not complete.")
    else:
        print(f"{'PASS' if result.last_test.passed else 'FAIL'} "
              f"(exit code {result.last_test.returncode})")
        print(result.last_test.output)
    print(f"Repair {'succeeded' if result.passed else 'failed'}.")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
