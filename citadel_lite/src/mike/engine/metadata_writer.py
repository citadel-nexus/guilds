import json
from pathlib import Path
try:
    from config.config_loader import load_config
except (ImportError, ModuleNotFoundError):
    from src.mike.config.config_loader import load_config
from datetime import datetime, timezone

config = load_config()
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / config["metadata_output_path"]

def save_vector_metadata(packet: dict):
    """
    処理済みの意味構造（soul packet）をJSONL形式で追記保存する。
    """
    # === HOUSE構造向け初期化 ===
    if packet.get("tier") in [None, ""]:
        packet["tier"] = "L1"
    if packet.get("hit_count") in [None, ""]:
        packet["hit_count"] = 0
    if packet.get("last_accessed") in [None, ""]:
        packet["last_accessed"] = datetime.now(timezone.utc).isoformat()

    line = json.dumps(packet, ensure_ascii=False)
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    # トレースログ（vector_id付き）
    vector_id = packet.get("vector_id", "unknown_id")
    print(f"[TRACE] Metadata saved for vector_id: {vector_id}")
