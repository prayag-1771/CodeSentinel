from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DiffHunk:
    header: str
    added_lines: int = 0
    removed_lines: int = 0


@dataclass(slots=True)
class DiffFilePatch:
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)


def load_diff_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_unified_diff(diff_text: str) -> list[DiffFilePatch]:
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


def _normalize_diff_path(value: str) -> str:
    value = value.strip()
    if value in {"/dev/null", "a/dev/null", "b/dev/null"}:
        return value
    if value.startswith("a/") or value.startswith("b/"):
        return value[2:]
    return value