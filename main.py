from __future__ import annotations

import argparse
from pathlib import Path

from diff_parser import format_diff_summary, load_diff_file, parse_unified_diff, review_unified_diff
from review_engine import analyze_file, analyze_source, build_demo_source, format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI code review prototype for Python files")
    parser.add_argument("path", nargs="?", help="Path to a Python file to review")
    parser.add_argument("--demo", action="store_true", help="Review the built-in sample code")
    parser.add_argument("--diff-file", help="Path to a unified diff file to inspect")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.demo:
        report = analyze_source(build_demo_source(), target_name="demo.py")
    elif args.diff_file:
        diff_text = load_diff_file(Path(args.diff_file))
        file_patches = parse_unified_diff(diff_text)
        print(format_diff_summary(file_patches))
        findings = review_unified_diff(diff_text)
        if findings:
            print("")
            print("Patch review findings:")
            for finding in findings:
                location = f":{finding.line}" if finding.line is not None else ""
                print(f"- [{finding.severity}] {finding.category} ({finding.file_path}{location})")
                print(f"  {finding.message}")
                if finding.suggestion:
                    print(f"  Suggestion: {finding.suggestion}")
        else:
            print("")
            print("Patch review findings: none")
        return
    elif args.path:
        report = analyze_file(Path(args.path))
    else:
        parser.error("provide a path or pass --demo")

    print(format_report(report))


if __name__ == "__main__":
    main()
