# agent_2_elaborator.py

import sys
import os
import json
import random

from openai import OpenAI
from .llm_client import get_llm_client
from ..devhelper.safe_json_utils import safe_parse_enrichment_response

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_client = None
_default_model = None

def _get_client():
    global _client, _default_model
    if _client is None:
        _client, _default_model = get_llm_client()
    return _client, _default_model

def run_agent_2(prompt: str, model=None) -> dict:
    """Agent_2: 入力プロンプトを15項目のメタ情報付きJSONで展開"""

    client, default_model = _get_client()
    use_model = model or default_model
    response = client.chat.completions.create(
        model=use_model,
        temperature=0.7,
        max_tokens=800,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Agent 2 (Elaborator) in a classified AI cognition pipeline.\n"
                    "Your task is to elaborate an idea by generating a JSON object with EXACTLY the following 19 enrichment fields:\n\n"
                    "['refined_text', 'elaboration_quality', 'real_world_analogy', 'context_enrichment_score', 'emotional_association',\n"
                    "'cross_domain_integration', 'explanation_length', 'narrative_clarity', 'educational_tier',\n"
                    "'domain_generalization', 'transferable_logic', 'applied_scenarios', 'familiarity_rating',\n"
                    "'nonlinearity_score', 'analogy_density', 'concept_resonance_score',\n"
                    "'topic_label', 'key_entities', 'language']\n\n"
                    "⚠️ Format Instructions:\n"
                    "- The first field must be 'refined_text': a 1-2 sentence concise rephrasing of the idea.\n"
                    "- 'topic_label' must be a short, high-level title for the idea (like a topic or headline).\n"
                    "- 'key_entities' must be a list (array) of 1–7 important proper nouns and entity names found in the idea\n"
                    "  (e.g., project names such as 'Zayara', tools like 'Citadel Helper', product names, libraries, or people).\n"
                    "- 'language' must be a short code such as 'ja' or 'en' indicating the primary language of the original idea.\n"
                    "- Return ONLY a valid JSON object with ALL fields present.\n"
                    "- Do NOT include markdown formatting (e.g., no triple backticks).\n"
                    "- Do NOT include explanations, comments, or extra keys.\n"
                    "- Each value must be contextually intelligent and relevant to the idea.\n"
                    "- Use plain text, numbers, or strings as needed."
                )
            },
            {
                "role": "user",
                "content": f"Elaborate on the following concept with rich insight:\n\n{prompt}"
            }
        ]
    )
    # 応答パース（JSONとして扱えることが前提）
    try:
        raw = response.choices[0].message.content.strip()
        parsed = safe_parse_enrichment_response(raw)  # パースだけ（フィールド補完なし）

        # Phase4: 固有名詞メタを必ず持たせるためのデフォルト埋め
        parsed.setdefault("topic_label", "")
        parsed.setdefault("key_entities", [])
        parsed.setdefault("language", "")

        return parsed
    except json.JSONDecodeError:
        print("❌ Agent_2 からの応答がJSON形式ではありません：")
        print(response.choices[0].message.content)
        raise
