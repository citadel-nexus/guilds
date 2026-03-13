#!/usr/bin/env bash
# =============================================================================
# ci/translate_evolve_publish.sh
# Citadel Lite — CI pipeline: translate → evolve → publish
#
# Compatible with:
#   - GitHub Actions  ($GITHUB_WORKSPACE)
#   - GitLab CI/CD    ($CI_PROJECT_DIR)
#   - Local execution (auto-detects repo root via git)
#
# Environment variables:
#   CITADEL_DRY_RUN       Set to "1" to skip live Notion/Supabase writes
#   CITADEL_GGUF_MODEL    Path to GGUF model file (optional)
#   NOTION_TOKEN          Notion integration token
#   SUPABASE_URL          Supabase project URL
#   CITADEL_INPUT_PATHS   Space-separated source file paths (default: auto-detect)
#   CITADEL_OUT_DIR       Output directory (default: out/ir)
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------
if [ -n "${GITHUB_WORKSPACE:-}" ]; then
    PROJECT_ROOT="$GITHUB_WORKSPACE"
elif [ -n "${CI_PROJECT_DIR:-}" ]; then
    PROJECT_ROOT="$CI_PROJECT_DIR"
else
    PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

echo "[citadel-ci] Project root: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DRY_RUN="${CITADEL_DRY_RUN:-0}"
OUT_DIR="${CITADEL_OUT_DIR:-out/ir}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
IR_JSON="${OUT_DIR}/roadmap_ir_${TIMESTAMP}.json"
IR_REPORT="${OUT_DIR}/roadmap_ir_${TIMESTAMP}.report.md"

mkdir -p "$OUT_DIR"

# ---------------------------------------------------------------------------
# Step 1: Translate — source documents → Roadmap IR JSON
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 1: Translate ==="

# Auto-detect input files if not specified
if [ -z "${CITADEL_INPUT_PATHS:-}" ]; then
    INPUT_ARGS=""
    for f in README.md README.ja.md; do
        [ -f "$f" ] && INPUT_ARGS="$INPUT_ARGS $f"
    done
    for f in old/Citadel_lite_RoadMap_*.md EVOLUTION_ROADMAP_*.md; do
        [ -f "$f" ] && INPUT_ARGS="$INPUT_ARGS $f"
    done
    for f in old/IMPLEMENTATION_SUMMARY_*.md; do
        [ -f "$f" ] && INPUT_ARGS="$INPUT_ARGS $f"
    done
else
    INPUT_ARGS="${CITADEL_INPUT_PATHS}"
fi

if [ -z "${INPUT_ARGS:-}" ]; then
    echo "[citadel-ci] WARNING: No input files found. Skipping translate step."
else
    echo "[citadel-ci] Input files:${INPUT_ARGS}"
    python -m src.roadmap_translator.cli \
        translate \
        --output-json "$IR_JSON" \
        --output-report "$IR_REPORT" \
        ${INPUT_ARGS}
    echo "[citadel-ci] IR written to: $IR_JSON"
fi

# ---------------------------------------------------------------------------
# Step 2: Evolve — run MCA evolution cycle (dry_run safe)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: Evolve ==="

EVOLVE_FLAGS=""
[ "$DRY_RUN" = "1" ] && EVOLVE_FLAGS="--dry-run"

if python -c "from src.mca.cli import main" 2>/dev/null; then
    python -m src.mca.cli evolve ${EVOLVE_FLAGS} || {
        echo "[citadel-ci] WARNING: evolve step failed — continuing."
    }
else
    echo "[citadel-ci] src.mca.cli not available — skipping evolve step."
fi

# ---------------------------------------------------------------------------
# Step 3: Publish — push results to Notion/Supabase
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: Publish ==="

PUBLISH_FLAGS=""
[ "$DRY_RUN" = "1" ] && PUBLISH_FLAGS="--dry-run"

if [ -z "${NOTION_TOKEN:-}" ] && [ -z "${SUPABASE_URL:-}" ]; then
    echo "[citadel-ci] No NOTION_TOKEN or SUPABASE_URL set — skipping publish step."
elif python -c "from src.mca.notion_bridge import publish_evo_result" 2>/dev/null; then
    python -m src.mca.cli publish ${PUBLISH_FLAGS} || {
        echo "[citadel-ci] WARNING: publish step failed — continuing."
    }
else
    echo "[citadel-ci] src.mca.notion_bridge not available — skipping publish step."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "=== Citadel CI pipeline complete ==="
echo "  DRY_RUN: $DRY_RUN"
echo "  IR JSON: ${IR_JSON}"
echo "  Report:  ${IR_REPORT}"
