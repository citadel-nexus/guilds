# agent_3_reflector.py

import sys
import os
import json
import uuid
import random

from .llm_client import get_llm_client
from datetime import datetime, timezone
from ..devhelper.safe_json_utils import safe_parse_reflection_response

_client = None
_default_model = None

def _get_client():
    global _client, _default_model
    if _client is None:
        _client, _default_model = get_llm_client()
    return _client, _default_model



from .embedding_tools import get_embedding

def get_resonance_vector(text: str) -> list[float]:
    """
    Always use embedding_tools for resonance vectors (OpenAI API, 1536-dim).
    """
    vector = get_embedding(text)
    return vector.tolist() if vector is not None else []



def run_agent_3(refined_text: str, model=None) -> dict:
    """
    Agent 3: refined_text をもとに自己評価＋メタデータ＋reflection_textを返す。
    resonance_vectorはOpenAI埋め込みベクトルで統一。
    """
    system_prompt = (
        "You are a reflection and evaluation agent."
        "Your job is to interpret the meaning and quality of a given input and generate a reflection on it."
        "Your response must be a valid JSON object with at least the following fields:"
        "['primary_intent', 'anticipated_impact', 'judgment_basis', 'emotion_profile',"
        " 'reflection_score', 'trust_score', 'clarity_score', 'insight_score', 'logic_quality_score',"
        " 'self_rating', 'human_echo_score', 'resonance_vector', 'lineage', 'timestamp',"
        " 'reflection_text']"
        "You MAY also include optional fields such as 'topic_label' (a short topic title for the idea)"
        " and 'key_entities' (a list of important proper nouns / entity names like 'Zayara', 'Citadel Helper')."
        "- Each score must be a float from 0.0 to 1.0."
        "- If you are unsure about any score, return a best estimate."
        "- Return only the JSON object, without explanation or markdown."
    )
    user_prompt = f"Reflect on the following refined idea:\n\n{refined_text}\n\nInclude a 'reflection_text' field."

    try:
        client, default_model = _get_client()
        use_model = model or default_model
        response = client.chat.completions.create(
            model=use_model,
            temperature=0.7,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        content = response.choices[0].message.content.strip()
        print("=== Agent 3 raw content ===")
        print(content)

        if content.startswith("```") and "json" in content:
            content = content.split("```")[1].replace("json", "", 1).strip()

        # 3) safe_parse_reflection_response で JSON をパース
        parsed = safe_parse_reflection_response(content)

        # --- 正規化（必ず現在時刻／型揃え） ---
        src_ts = parsed.pop("timestamp", None)
        if src_ts:
            parsed["source_timestamp"] = src_ts  # LLMが返した値は退避のみ
        parsed["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        lin = parsed.get("lineage")
        if isinstance(lin, str):
            parsed["source_lineage"] = lin
            parsed["lineage"] = [lin]
        elif not isinstance(lin, list):
            parsed["lineage"] = [f"soul_{uuid.uuid4().hex[:8]}"]

        # 4) resonance_vector を追加
        parsed["resonance_vector"] = list(get_resonance_vector(refined_text))
        parsed.setdefault("reflection_score", 0.0)
        parsed.setdefault("reflection_text", "")

        # Phase4: topic_label / key_entities を必ず持たせる（Agent2 が無い場合の保険）
        # すでに LLM 応答内にあればそれを尊重し、無ければ簡易的に埋める。
        parsed.setdefault("topic_label", parsed.get("primary_intent", "") or "")
        if "key_entities" not in parsed:
            parsed["key_entities"] = []

        # 正規化後の出力（人が読むログはこちら）
        if os.getenv("USE_AGENT3_NORMALIZED_LOG", "1") == "1":
            print("=== Agent 3 normalized ===")
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        
        # 🔽 HOUSE 初期値の追加
        parsed.setdefault("tier", "L1")
        parsed.setdefault("hit_count", 0)
        parsed.setdefault("last_accessed", datetime.now(timezone.utc).isoformat())
        return parsed

    except json.JSONDecodeError:
        print("❌ Agent_3 returned invalid JSON:")
        print(content)
        raise
        
    except Exception as e:
        print(f"❌ Agent_3 で例外発生: {e}")
        # 最低限のフィールドだけを持つデフォルト辞書を返す
        return {
            "primary_intent": "",
            "anticipated_impact": "",
            "judgment_basis": "",
            "emotion_profile": "",
            "reflection_score": 0.0,
            "trust_score": 0.0,
            "resonance_vector": [],  # エラー時は安全に空リスト
            "lineage": [f"soul_{uuid.uuid4().hex[:8]}"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reflection_text": ""
        }
    

