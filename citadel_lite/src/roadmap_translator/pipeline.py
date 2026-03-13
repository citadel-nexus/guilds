"""Roadmap Translator pipeline — Ingest→Detect→Translate→Normalize→Merge→Validate→Emit.

Orchestrates the full translation flow from source documents to Roadmap IR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Type

from src.roadmap_ir.types import Conflict, Item, Note, RoadmapIR, Source
from src.roadmap_ir.validators import validate_ir
from src.roadmap_translator.detect import detect_translator
from src.roadmap_translator.emit import build_ir, emit_json, emit_report
from src.roadmap_translator.ingest import ingest_file
from src.roadmap_translator.merge import merge_items
from src.roadmap_translator.normalize import normalize_items
from src.roadmap_translator.translators.base import BaseTranslator, TranslationPatch
from src.roadmap_translator.translators.implementation_summary import (
    ImplSummaryTranslator,
)
from src.roadmap_translator.translators.markdown_roadmap import (
    MarkdownRoadmapTranslator,
)
from src.roadmap_translator.translators.readme import ReadmeTranslator
from src.roadmap_translator.translators.gitlog import GitlogTranslator
from src.roadmap_translator.translators.generic_markdown import (
    GenericMarkdownTranslator,
)

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "translator_pipeline"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1

# ---------------------------------------------------------------------------
# Default translator registry
# ---------------------------------------------------------------------------
DEFAULT_TRANSLATORS: List[Type[BaseTranslator]] = [
    ReadmeTranslator,
    MarkdownRoadmapTranslator,
    ImplSummaryTranslator,
    GitlogTranslator,
    GenericMarkdownTranslator,  # fallback — must be last
]


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------
@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    ir: RoadmapIR
    json_path: Optional[Path] = None
    report_path: Optional[Path] = None
    notes: List[Note] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_pipeline(
    input_paths: List[Path],
    output_json: Optional[Path] = None,
    output_report: Optional[Path] = None,
    translators: Optional[List[Type[BaseTranslator]]] = None,
) -> PipelineResult:
    """Run the full Ingest→Detect→Translate→Normalize→Merge→Validate→Emit pipeline.

    Args:
        input_paths: list of source document paths.
        output_json: optional path to write roadmap_ir.json.
        output_report: optional path to write roadmap_ir.report.md.
        translators: translator classes to use (defaults to all 3).

    Returns:
        PipelineResult with the assembled IR and output paths.
    """
    if translators is None:
        translators = DEFAULT_TRANSLATORS

    # Phase 1: Ingest
    sources: List[Source] = []
    patches: List[TranslationPatch] = []

    for path in input_paths:
        source, lines = ingest_file(path)
        sources.append(source)

        # Phase 2: Detect
        translator_cls = detect_translator(path, lines, translators)
        if translator_cls is None:
            continue

        # Phase 3: Translate
        translator = translator_cls()
        patch = translator.translate(lines, source.source_id)
        patches.append(patch)

    # Phase 4: Normalize
    for patch in patches:
        normalize_items(patch.items)

    # Phase 5: Merge
    patches_items = [(p.source_id, p.items) for p in patches]
    merged_items, conflicts = merge_items(patches_items)

    # Phase 6: Validate
    # Build preliminary IR for validation
    ir = build_ir(sources, merged_items, conflicts, notes=[])
    validation_notes = validate_ir(ir)

    # Phase 7: Emit (rebuild with notes)
    ir = build_ir(sources, merged_items, conflicts, notes=validation_notes)

    result = PipelineResult(ir=ir, notes=validation_notes)

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        emit_json(ir, output_json)
        result.json_path = output_json

    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        emit_report(ir, output_report)
        result.report_path = output_report

    return result
