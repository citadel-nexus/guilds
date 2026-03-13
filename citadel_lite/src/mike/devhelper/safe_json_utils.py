import json
from datetime import datetime

def safe_parse_reflection_response(content):
    """GPTから返された文字列を安全にパースして必要フィールドを補完"""
    content = content.strip()

    # コードブロック "```" からJSON部分を取り出す
    if content.startswith("```") and "json" in content:
        content = content.split("```", 1)[1].replace("json", "", 1).strip()

    try:
        parsed = json.loads(content)
        
        # 型チェックを追加
        if not isinstance(parsed, dict):
            print("❌ Parsed JSON is not a dictionary. Auto-recovering to empty object.")
            parsed = {}
        
    except json.JSONDecodeError:
        print("❌ Invalid JSON detected from Agent 3. Attempting to auto-recover...")
        parsed = {}

    # 必須フィールドを補完
    return ensure_reflection_fields(parsed)

def ensure_reflection_fields(data):
    """データに必須フィールドがない場合、デフォルト値を追加する"""
    fixed = {
        "primary_intent": data.get("primary_intent", None),
        "anticipated_impact": data.get("anticipated_impact", None),
        "judgment_basis": data.get("judgment_basis", None),
        "emotion_profile": data.get("emotion_profile", {
            "curiosity": 0.0,
            "insight": 0.0,
            "skepticism": 0.0,
            "engagement": 0.0
        }),
        "reflection_score": data.get("reflection_score", 0.0),
        "trust_score": data.get("trust_score", None),  # ← ★これを追加！
        "resonance_vector": data.get("resonance_vector", []),
        "lineage": data.get("lineage", []),
        "timestamp": data.get("timestamp", datetime.now().isoformat()),
        "reflection_text": data.get("reflection_text", "No reflection text provided."),
    }
    return fixed


def safe_parse_enrichment_response(content):
    """Agent2向け: GPT出力を安全にパース（フィールド補完なし）"""
    content = content.strip()

    # コードブロック "```" からJSON部分を取り出す
    if content.startswith("```") and "json" in content:
        content = content.split("```", 1)[1].replace("json", "", 1).strip()

    try:
        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            print("❌ Parsed JSON is not a dictionary. Auto-recovering to empty object.")
            parsed = {}

    except json.JSONDecodeError:
        print("❌ Invalid JSON detected from Agent 2. Attempting to auto-recover...")
        parsed = {}

    return parsed