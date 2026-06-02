from __future__ import annotations

import argparse
import os
from pathlib import Path
from dotenv import load_dotenv

from diff_parser import format_diff_summary, load_diff_file, parse_unified_diff, review_unified_diff
from review_engine import analyze_file, analyze_source, build_demo_source, format_report
from github_integration import parse_pr_url, fetch_pr_diff, submit_pr_review, submit_pr_comment

# Load environment variables from .env file
load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI code review prototype for Python files")
    parser.add_argument("path", nargs="?", help="Path to a Python file to review")
    parser.add_argument("--demo", action="store_true", help="Review the built-in sample code")
    parser.add_argument("--diff-file", help="Path to a unified diff file to inspect")
    parser.add_argument("--github-pr", help="GitHub PR URL or ID to review (e.g. owner/repo#123 or https://github.com/owner/repo/pull/123)")
    parser.add_argument("--github-token", help="GitHub API Access Token (defaults to GITHUB_TOKEN environment variable)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.github_pr:
        # 1. Parse GitHub PR reference
        try:
            pr_info = parse_pr_url(args.github_pr)
        except ValueError as e:
            parser.error(str(e))

        # 2. Get GitHub Access Token
        token = args.github_token or os.getenv("GITHUB_TOKEN")
        if not token:
            parser.error(
                "GitHub integration requires a token. Pass --github-token or set the GITHUB_TOKEN environment variable."
            )

        # 3. Fetch PR unified diff
        print(f"Fetching diff for Pull Request #{pr_info.pr_number} from {pr_info.owner}/{pr_info.repo}...")
        try:
            diff_text = fetch_pr_diff(pr_info, token)
        except Exception as e:
            print(f"Error fetching PR diff: {e}")
            return

        # 4. Review diff findings
        print("Analyzing changes...")
        findings = review_unified_diff(diff_text)

        # 5. Format and submit findings to GitHub
        inline_comments = []
        summary_findings_lines = []

        for finding in findings:
            if finding.line is not None:
                # Format the inline comment body
                comment_body = f"### ⚠️ CodeSentinel Finding: {finding.category}\n"
                comment_body += f"**Severity:** `{finding.severity}`\n\n"
                comment_body += f"{finding.message}\n"
                if finding.suggestion:
                    comment_body += f"\n**Suggestion:**\n{finding.suggestion}"

                inline_comments.append({
                    "path": finding.file_path,
                    "line": finding.line,
                    "side": "RIGHT",
                    "body": comment_body
                })
            else:
                loc = f" in `{finding.file_path}`" if finding.file_path else ""
                finding_text = f"- **[{finding.severity}]** {finding.category}{loc}: {finding.message}"
                if finding.suggestion:
                    finding_text += f" (Suggestion: {finding.suggestion})"
                summary_findings_lines.append(finding_text)

        # Build main review summary body
        review_body = "## 🤖 CodeSentinel PR Review Report\n\n"
        if findings:
            review_body += f"Detected **{len(findings)}** code quality findings/issues.\n\n"
            if summary_findings_lines:
                review_body += "### 📋 General/File-level Findings\n"
                review_body += "\n".join(summary_findings_lines) + "\n\n"
            if inline_comments:
                review_body += "Please see the inline comments below for line-specific feedback."
        else:
            review_body += "🎉 No code quality issues detected by the current rule set! Great job!"

        try:
            print("Submitting review with inline comments to GitHub...")
            submit_pr_review(pr_info, token, review_body, inline_comments)
            print("Successfully posted PR review comments!")
        except Exception as ex:
            print(f"Warning: Could not submit inline PR review comments: {ex}")
            print("Falling back to posting a single PR summary comment...")

            # Format all findings for the fallback summary comment
            fallback_body = "## 🤖 CodeSentinel PR Review Summary\n\n"
            if findings:
                fallback_body += f"We found **{len(findings)}** code quality issue(s) during inspection:\n\n"
                from collections import defaultdict
                by_file = defaultdict(list)
                for f in findings:
                    by_file[f.file_path].append(f)

                for file_path, file_findings in by_file.items():
                    fallback_body += f"### 📄 `{file_path}`\n"
                    for f in file_findings:
                        loc_str = f"Line {f.line}: " if f.line is not None else ""
                        fallback_body += f"- **[{f.severity}]** {f.category} — {loc_str}{f.message}\n"
                        if f.suggestion:
                            fallback_body += f"  - *Suggestion:* {f.suggestion}\n"
                    fallback_body += "\n"
            else:
                fallback_body += "🎉 No code quality issues detected by the current rule set! Great job!"

            try:
                submit_pr_comment(pr_info, token, fallback_body)
                print("Successfully posted summary fallback comment to PR!")
            except Exception as fallback_ex:
                print(f"Error: Failed to post fallback PR comment: {fallback_ex}")
        return

    elif args.demo:
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
        parser.error("provide a path or pass --demo, --diff-file, or --github-pr")

    print(format_report(report))


if __name__ == "__main__":
    main()

