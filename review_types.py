from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ReviewFinding:
    category: str
    severity: str
    message: str
    line: int | None = None
    suggestion: str | None = None


@dataclass(slots=True)
class ReviewReport:
    target_name: str
    quality_score: int
    findings: list[ReviewFinding] = field(default_factory=list)