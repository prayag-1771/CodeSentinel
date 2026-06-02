from __future__ import annotations

import ast
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from textwrap import dedent

from review_types import ReviewFinding, ReviewReport


SEVERITY_WEIGHTS = {
    "high": 18,
    "medium": 10,
    "low": 5,
}


def build_demo_source() -> str:
    return dedent(
        '''
        import requests
        import not_a_real_package

        def _format_user(user):
            return format_user(user)

        def format_user(user):
            return format_user(user)

        def format_user_copy(user):
            return format_user(user)

        def build_payload(user):
            return {
                "name": user["name"],
                "role": user["role"],
            }

        def build_payload_again(user):
            return {
                "name": user["name"],
                "role": user["role"],
            }

        def risky_step():
            try:
                return do_work()
            except Exception:
                pass
        '''
    ).strip()


def analyze_file(path: Path) -> ReviewReport:
    source = path.read_text(encoding="utf-8")
    return analyze_source(source, target_name=path.name, file_path=path)


def analyze_source(source: str, target_name: str, file_path: Path | None = None) -> ReviewReport:
    tree = ast.parse(source)
    findings: list[ReviewFinding] = []

    findings.extend(_find_hallucinated_imports(tree))
    findings.extend(_find_dead_code(tree))
    findings.extend(_find_unnecessary_abstractions(tree))
    findings.extend(_find_duplicate_logic(tree, source))
    findings.extend(_find_suspicious_patterns(tree, source))

    if file_path is not None:
        findings.extend(_find_missing_tests(file_path))

    quality_score = _score(findings)
    return ReviewReport(target_name=target_name, quality_score=quality_score, findings=findings)


def format_report(report: ReviewReport) -> str:
    lines = [f"AI Quality Score: {report.quality_score}/100", f"Target: {report.target_name}"]

    if not report.findings:
        lines.append("No obvious review issues detected by the current rule set.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Findings:")
    for finding in report.findings:
        location = f"line {finding.line}" if finding.line is not None else "no line"
        lines.append(f"- [{finding.severity}] {finding.category} ({location})")
        lines.append(f"  {finding.message}")
        if finding.suggestion:
            lines.append(f"  Suggestion: {finding.suggestion}")
    return "\n".join(lines)


def _score(findings: list[ReviewFinding]) -> int:
    penalty = sum(SEVERITY_WEIGHTS.get(finding.severity, 5) for finding in findings)
    return max(0, 100 - penalty)


def _find_hallucinated_imports(tree: ast.AST) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".", 1)[0]
                if not _module_exists(module_name):
                    findings.append(
                        ReviewFinding(
                            category="Hallucinated import",
                            severity="high",
                            line=node.lineno,
                            message=f"Import '{alias.name}' could not be resolved in this environment.",
                            suggestion="Remove the import or add the missing dependency to the project.",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None or node.level > 0:
                continue
            module_name = node.module.split(".", 1)[0]
            if not _module_exists(module_name):
                findings.append(
                    ReviewFinding(
                        category="Hallucinated import",
                        severity="high",
                        line=node.lineno,
                        message=f"Module '{node.module}' could not be resolved in this environment.",
                        suggestion="Remove the import or add the missing dependency to the project.",
                    )
                )
    return findings


def _find_dead_code(tree: ast.AST) -> list[ReviewFinding]:
    defined: dict[str, ast.AST] = {}
    used_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined[node.name] = node
        elif isinstance(node, ast.Name):
            used_names.add(node.id)

    findings: list[ReviewFinding] = []
    for name, node in defined.items():
        if name.startswith("_") and name not in used_names:
            findings.append(
                ReviewFinding(
                    category="Dead code",
                    severity="medium",
                    line=getattr(node, "lineno", None),
                    message=f"'{name}' is defined but never referenced inside this file.",
                    suggestion="Delete the helper or wire it into the code path that needs it.",
                )
            )
    return findings


def _find_unnecessary_abstractions(tree: ast.AST) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or len(node.body) != 1:
            continue
        only_statement = node.body[0]
        if not isinstance(only_statement, ast.Return):
            continue
        if not isinstance(only_statement.value, ast.Call):
            continue
        if isinstance(only_statement.value.func, ast.Name) and only_statement.value.func.id == node.name:
            continue

        findings.append(
            ReviewFinding(
                category="Unnecessary abstraction",
                severity="medium",
                line=node.lineno,
                message=f"'{node.name}' only forwards to another call and may not need its own wrapper.",
                suggestion="Inline the wrapper unless it adds a real boundary, validation step, or abstraction.",
            )
        )
    return findings


def _find_duplicate_logic(tree: ast.AST, source: str) -> list[ReviewFinding]:
    bodies: defaultdict[str, list[ast.AST]] = defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_segments = []
            for stmt in node.body:
                seg = ast.get_source_segment(source, stmt)
                if seg:
                    body_segments.append(seg)
            if not body_segments:
                continue
            normalized = "\n".join(line.strip() for seg in body_segments for line in seg.splitlines() if line.strip())
            bodies[normalized].append(node)

    findings: list[ReviewFinding] = []
    for nodes in bodies.values():
        if len(nodes) < 2:
            continue
        line = min(node.lineno for node in nodes)
        findings.append(
            ReviewFinding(
                category="Duplicate logic",
                severity="medium",
                line=line,
                message="Two or more functions have the same body shape, which is a common AI-generated duplication smell.",
                suggestion="Extract the shared logic into one function and call it from both places.",
            )
        )
    return findings


def _find_suspicious_patterns(tree: ast.AST, source: str) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    source_text = source.lower()
    if "todo" in source_text or "fixme" in source_text:
        findings.append(
            ReviewFinding(
                category="Suspicious AI-generated pattern",
                severity="low",
                message="The file still contains TODO/FIXME markers.",
                suggestion="Replace placeholders with a concrete implementation or remove the unfinished path.",
            )
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(
                    ReviewFinding(
                        category="Suspicious AI-generated pattern",
                        severity="high",
                        line=node.lineno,
                        message="A broad exception handler swallows the error and does nothing.",
                        suggestion="Narrow the exception or log and re-raise it so failures stay visible.",
                    )
                )
    return findings


def _find_missing_tests(file_path: Path) -> list[ReviewFinding]:
    if "test" in file_path.stem.lower():
        return []

    candidate_names = {
        f"test_{file_path.stem}.py",
        file_path.name.replace(".py", "_test.py"),
    }
    has_tests = any((file_path.parent / candidate).exists() for candidate in candidate_names)
    if has_tests:
        return []

    tests_dir = file_path.parent / "tests"
    if tests_dir.exists():
        return []

    return [
        ReviewFinding(
            category="Missing tests",
            severity="medium",
            message=f"No obvious test file was found for '{file_path.name}'.",
            suggestion="Add a focused unit test that covers the main success path and one failure path.",
        )
    ]


def _module_exists(module_name: str) -> bool:
    if module_name in sys.stdlib_module_names:
        return True
    return importlib.util.find_spec(module_name) is not None