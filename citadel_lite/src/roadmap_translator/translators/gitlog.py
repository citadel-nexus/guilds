"""Git log translator — parses ``git log`` text output into EvidenceGit items.

Expected input format (``git log --pretty=format:"%H%n%an%n%ai%n%s" --name-only``):

    abc1234def5678...
    Author Name
    2026-02-25 10:00:00 +0900
    Phase 22: Add execution runner

    src/execution/runner_v2.py
    tests/test_execution.py

Each commit block is separated by a blank line after the file list.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional

from src.roadmap_ir.types import (
    EvidenceGit,
    EvidenceText,
    Item,
    ItemKindEnum,
    StatusEnum,
    VerifyEnum,
)
from src.roadmap_translator.translators.base import BaseTranslator, TranslationPatch

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_gitlog"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# FILE_PHASE_MAP: file path pattern → phase number
# ---------------------------------------------------------------------------
FILE_PHASE_MAP: Dict[str, int] = {
    "agents/": 1,
    "execution/": 2,
    "memory/": 3,
    "cgrf/": 4,
    "monitoring/": 5,
    "mca/": 6,
    "infra/": 7,
    "roadmap": 8,
    "ci/": 8,
    "tests/": 0,      # test files → phase 0 (normalizer will handle)
}

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_COMMIT_HASH_RE = re.compile(r"^(?P<hash>[0-9a-f]{7,40})\s*$")
_DATE_RE = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"[T ](?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)
_FILE_LINE_RE = re.compile(r"^[a-zA-Z0-9_./-]")  # Loose: any path-like line


def _map_files_to_phase(files: List[str]) -> Optional[int]:
    """Return the first matched phase from FILE_PHASE_MAP, else None."""
    for f in files:
        for pattern, phase in FILE_PHASE_MAP.items():
            if pattern in f:
                return phase if phase > 0 else None
    return None


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse ISO-ish datetime string."""
    m = _DATE_RE.match(date_str.strip())
    if not m:
        return None
    try:
        return datetime(
            int(m.group("year")), int(m.group("month")), int(m.group("day")),
            int(m.group("hour")), int(m.group("minute")), int(m.group("second")),
        )
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------

class GitlogTranslator(BaseTranslator):
    """Extracts items from ``git log`` formatted text output."""

    @property
    def name(self) -> str:
        return "gitlog"

    def translate(
        self, lines: List[str], source_id: str
    ) -> TranslationPatch:
        patch = TranslationPatch(source_id=source_id)

        # Parse commit blocks
        commits = self._split_commits(lines)
        for commit in commits:
            item = self._parse_commit(commit, source_id)
            if item is not None:
                patch.items.append(item)

        return patch

    # ------------------------------------------------------------------

    def _split_commits(self, lines: List[str]) -> List[List[str]]:
        """Split lines into per-commit blocks (split at blank lines between commits)."""
        commits: List[List[str]] = []
        current: List[str] = []

        for line in lines:
            stripped = line.rstrip()

            if _COMMIT_HASH_RE.match(stripped) and current:
                # New commit starts — flush previous
                if any(l.strip() for l in current):
                    commits.append(current)
                current = [stripped]
            else:
                current.append(stripped)

        if any(l.strip() for l in current):
            commits.append(current)

        return commits

    def _parse_commit(
        self, block: List[str], source_id: str
    ) -> Optional[Item]:
        """Parse a single commit block into an Item."""
        non_empty = [l for l in block if l.strip()]
        if len(non_empty) < 2:
            return None

        # Line 0: commit hash
        hash_m = _COMMIT_HASH_RE.match(non_empty[0])
        if not hash_m:
            return None
        commit_hash = hash_m.group("hash")

        # Line 1: author
        author = non_empty[1].strip() if len(non_empty) > 1 else None

        # Line 2: date
        date: Optional[datetime] = None
        message_start = 3
        if len(non_empty) > 2:
            date = _parse_date(non_empty[2])
            if date is None:
                # Date line missing — shift
                message_start = 2

        # Line 3: commit message (subject)
        message: Optional[str] = None
        if len(non_empty) > message_start - 1:
            message = non_empty[message_start - 1].strip() if len(non_empty) >= message_start else None

        # Remaining lines: changed files
        files = [
            l.strip()
            for l in non_empty[message_start:]
            if _FILE_LINE_RE.match(l.strip()) and l.strip()
        ]

        # Phase detection: message first, then file map
        phase: Optional[int] = None
        if message:
            phase = self.extract_phase(message)
        if phase is None:
            phase = _map_files_to_phase(files)

        # Status: if message contains "Phase N:" → treat as done
        status = StatusEnum.done if (message and re.search(r"Phase\s*\d+", message)) else StatusEnum.unknown

        # EvidenceGit
        ev = EvidenceGit(
            source_id=source_id,
            commit=commit_hash[:40],
            date=date,
            author=author[:200] if author else None,
            files=files[:20] if files else None,
            message=message[:500] if message else None,
            weight=0.7,
        )

        # Fallback text evidence if no EvidenceGit validates
        item_id = f"git-{commit_hash[:7]}"
        # Ensure item_id has valid format (min 4 chars after 'git-')
        if len(item_id) < 4:
            item_id = f"git-{commit_hash[:7]}-item"

        title = message[:100] if message else f"commit {commit_hash[:7]}"

        return Item(
            item_id=item_id,
            kind=ItemKindEnum.milestone,
            phase=phase,
            title=title,
            status=status,
            verify_status=VerifyEnum.unknown,
            evidence=[ev],
            raw={
                "commit": commit_hash,
                "files": files,
            },
        )
