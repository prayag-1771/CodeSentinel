from __future__ import annotations

import argparse
from pathlib import Path

from review_engine import analyze_file, analyze_source, build_demo_source, format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI code review prototype for Python files")
    parser.add_argument("path", nargs="?", help="Path to a Python file to review")
    parser.add_argument("--demo", action="store_true", help="Review the built-in sample code")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.demo:
        report = analyze_source(build_demo_source(), target_name="demo.py")
    elif args.path:
        report = analyze_file(Path(args.path))
    else:
        parser.error("provide a path or pass --demo")

    print(format_report(report))


if __name__ == "__main__":
    main()
