"""Roadmap IR enricher — post-validation GGUF/rule-based enrichment.

Called after ``validate_ir()`` to augment each ``Item.raw`` dict with:
  - ``summary``: concise text summary of the item
  - ``recommendations``: actionable next-step string
  - ``risk_notes``: risk flags based on item state and keywords

No Item fields are mutated; all enrichment is stored in ``Item.raw``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from src.roadmap_ir.types import Item, RoadmapIR
from src.roadmap import gguf_engine

# ---------------------------------------------------------------------------
# CGRF Tier 1 metadata
# ---------------------------------------------------------------------------
_MODULE_NAME = "roadmap_enricher"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_ir(
    ir: RoadmapIR,
    model: Optional[Any] = None,
) -> RoadmapIR:
    """Enrich all items in *ir* and return a new RoadmapIR.

    Args:
        ir: A validated RoadmapIR.
        model: Optional pre-loaded GGUF model (from ``gguf_engine.load_model()``).
               When ``None``, the engine will attempt to load from the
               ``CITADEL_GGUF_MODEL`` environment variable; if unavailable,
               rule-based generation is used.

    Returns:
        A new ``RoadmapIR`` with enriched items (``raw`` dicts updated).
    """
    if model is None:
        model = gguf_engine.load_model()  # None if no model configured

    enriched_items = [_enrich_item(item, model) for item in ir.items]

    # Rebuild IR with enriched items (preserving all other fields)
    return ir.model_copy(update={"items": enriched_items})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enrich_item(item: Item, model: Optional[Any]) -> Item:
    """Return a copy of *item* with enrichment data in ``raw``."""
    # Build prompt text from title + evidence
    evidence_text = " ".join(
        getattr(ev, "text", "") or getattr(ev, "message", "") or ""
        for ev in item.evidence
    )[:400]
    prompt_text = f"{item.title}. {evidence_text}".strip()

    # Summary
    summary = gguf_engine.generate_text(prompt_text, model=model, max_tokens=150)

    # Recommendations
    rec = gguf_engine.recommend(item.status.value, item.verify_status.value)

    # Risk notes
    risk_source = prompt_text
    if item.blockers:
        risk_source += " " + " ".join(b.text for b in item.blockers)
    risk = gguf_engine.generate_risk(risk_source)

    # Merge into existing raw (or create new dict)
    existing_raw: dict = dict(item.raw) if item.raw else {}
    existing_raw.update({
        "summary": summary,
        "recommendations": rec,
        "risk_notes": risk,
    })

    return item.model_copy(update={"raw": existing_raw})
