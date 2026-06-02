from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DiffHunk:
    header: str
    added_lines: int = 0
    removed_lines: int = 0
    lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiffFilePatch:
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)


@dataclass(slots=True)
class DiffReviewFinding:
    file_path: str
    category: str
    severity: str
    message: str
    line: int | None = None
    suggestion: str | None = None


def load_diff_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_unified_diff(diff_text: str) -> list[DiffFilePatch]:
    diff_text = diff_text.lstrip("\ufeff")
    files: list[DiffFilePatch] = []
    current_file: DiffFilePatch | None = None
    current_hunk: DiffHunk | None = None

    for raw_line in diff_text.splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("diff --git "):
            parts = line.split()
            old_path = _normalize_diff_path(parts[2]) if len(parts) > 2 else ""
            new_path = _normalize_diff_path(parts[3]) if len(parts) > 3 else old_path
            current_file = DiffFilePatch(old_path=old_path, new_path=new_path)
            files.append(current_file)
            current_hunk = None
            continue

        if current_file is None:
            continue

        if line.startswith("+++ "):
            current_file.new_path = _normalize_diff_path(line[4:])
            continue

        if line.startswith("--- "):
            current_file.old_path = _normalize_diff_path(line[4:])
            continue

        if line.startswith("@@ "):
            current_hunk = DiffHunk(header=line)
            current_file.hunks.append(current_hunk)
            continue

        if current_hunk is None:
            continue

        current_hunk.lines.append(line)
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.added_lines += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.removed_lines += 1

    return files


def format_diff_summary(file_patches: list[DiffFilePatch]) -> str:
    if not file_patches:
        return "No changed files detected in the diff."

    total_hunks = sum(len(file_patch.hunks) for file_patch in file_patches)
    total_additions = sum(hunk.added_lines for file_patch in file_patches for hunk in file_patch.hunks)
    total_deletions = sum(hunk.removed_lines for file_patch in file_patches for hunk in file_patch.hunks)

    lines = [
        f"Files changed: {len(file_patches)}",
        f"Hunks: {total_hunks}",
        f"Additions: {total_additions}",
        f"Deletions: {total_deletions}",
        "",
        "Changed files:",
    ]

    for file_patch in file_patches:
        file_name = file_patch.new_path or file_patch.old_path
        lines.append(f"- {file_name} ({len(file_patch.hunks)} hunks)")

    return "\n".join(lines)


def review_unified_diff(diff_text: str) -> list[DiffReviewFinding]:
    findings: list[DiffReviewFinding] = []
    file_patches = parse_unified_diff(diff_text)

    for file_patch in file_patches:
        file_path = file_patch.new_path or file_patch.old_path
        _review_patch_lines(file_path, file_patch, findings)
        if _is_new_file(file_patch):
            _review_new_file_source(file_patch, findings)
        else:
            _review_modified_file_source(file_patch, findings)

    return findings


def _normalize_diff_path(value: str) -> str:
    value = value.strip()
    if value in {"/dev/null", "a/dev/null", "b/dev/null"}:
        return value
    if value.startswith("a/") or value.startswith("b/"):
        return value[2:]
    return value


def _review_patch_lines(file_path: str, file_patch: DiffFilePatch, findings: list[DiffReviewFinding]) -> None:
    hunk_lines: list[str] = []
    for hunk in file_patch.hunks:
        hunk_lines.extend(hunk.lines)
    _flush_hunk_findings(file_path, hunk_lines, findings)


def _review_new_file_source(file_patch: DiffFilePatch, findings: list[DiffReviewFinding]) -> None:
    if not _is_new_file(file_patch):
        return

    source = _reconstruct_new_file_source(file_patch)
    if source is None:
        return

    try:
        from review_engine import analyze_source
    except ImportError:
        return

    try:
        report = analyze_source(source, target_name=file_patch.new_path or file_patch.old_path)
    except SyntaxError:
        return

    for finding in report.findings:
        findings.append(
            DiffReviewFinding(
                file_path=file_patch.new_path or file_patch.old_path,
                category=finding.category,
                severity=finding.severity,
                message=finding.message,
                line=finding.line,
                suggestion=finding.suggestion,
            )
        )


def _reconstruct_new_file_source(file_patch: DiffFilePatch) -> str | None:
    if not _is_new_file(file_patch):
        return None

    source_lines: list[str] = []
    for hunk in file_patch.hunks:
        for line in hunk.lines:
            if line.startswith("+") and not line.startswith("+++"):
                source_lines.append(line[1:])
    if not source_lines:
        return None
    return "\n".join(source_lines)


def _is_new_file(file_patch: DiffFilePatch) -> bool:
    return file_patch.old_path == "/dev/null" or file_patch.new_path == "/dev/null"


def _reconstruct_modified_file_source(file_patch: DiffFilePatch) -> str | None:
    """Reconstruct the new version of a modified file from its hunks."""
    if _is_new_file(file_patch):
        return None

    source_lines: list[str] = []
    for hunk in file_patch.hunks:
        for line in hunk.lines:
            # Context lines (start with space) or added lines (start with +) go into new file
            if line.startswith(" "):
                source_lines.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                source_lines.append(line[1:])
            # Removed lines (start with -) are skipped; they're not in the new file
    
    if not source_lines:
        return None
    return "\n".join(source_lines)


def _review_modified_file_source(file_patch: DiffFilePatch, findings: list[DiffReviewFinding]) -> None:
    """Run AST review on the reconstructed source of a modified file."""
    if _is_new_file(file_patch):
        return

    source = _reconstruct_modified_file_source(file_patch)
    if source is None:
        return

    try:
        from review_engine import analyze_source
    except ImportError:
        return

    try:
        report = analyze_source(source, target_name=file_patch.new_path or file_patch.old_path)
    except SyntaxError:
        return

    for finding in report.findings:
        findings.append(
            DiffReviewFinding(
                file_path=file_patch.new_path or file_patch.old_path,
                category=finding.category,
                severity=finding.severity,
                message=finding.message,
                line=finding.line,
                suggestion=finding.suggestion,
            )
        )


def _flush_hunk_findings(file_path: str, hunk_lines: list[str], findings: list[DiffReviewFinding]) -> None:
    if not file_path or not hunk_lines:
        return

    added_lines = [line[1:].strip() for line in hunk_lines if line.startswith("+") and not line.startswith("+++")]
    lowered_added = "\n".join(added_lines).lower()

    if any("import " in line for line in added_lines) and any("not_a_real_package" in line or "missing" in line for line in added_lines):
        findings.append(
            DiffReviewFinding(
                file_path=file_path,
                category="Hallucinated import",
                severity="high",
                message="The patch adds an import that looks unresolved or suspicious.",
            )
        )

    if "todo" in lowered_added or "fixme" in lowered_added:
        findings.append(
            DiffReviewFinding(
                file_path=file_path,
                category="Suspicious AI-generated pattern",
                severity="low",
                message="The patch still contains TODO/FIXME markers.",
            )
        )

    if any(line == "pass" for line in added_lines):
        findings.append(
            DiffReviewFinding(
                file_path=file_path,
                category="Suspicious AI-generated pattern",
                severity="high",
                message="The patch introduces a pass statement, which often hides unfinished work.",
            )
        )