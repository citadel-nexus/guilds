#agent_1_categorize.py

import openai
import os
import random
import json

from .llm_client import get_llm_client

_client = None
_default_model = None

def _get_client():
    global _client, _default_model
    if _client is None:
        _client, _default_model = get_llm_client()
    return _client, _default_model

def run_agent_1(raw_text, model=None):
    print("\n=== Agent_1 送信メッセージ ===")
    print(raw_text)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an intelligent categorization and tagging assistant.\n"
                "Please respond only in English.\n"
                "Your job is to analyze the user's idea and return a JSON object with two fields:\n"
                "1. 'category': a concise, high-level label summarizing the idea (this will be used as a topic label).\n"
                "2. 'tags': a list of 2 to 5 relevant keywords or short phrases.\n\n"
                "Tagging rules:\n"
                "- Always include important proper nouns and entity names as tags when they exist\n"
                "  (e.g., project names like 'Zayara', tools like 'Citadel Helper', product names, or people).\n"
                "- Also include 1–2 abstract/conceptual tags (e.g., 'search system', 'memory architecture').\n"
                "- Tags must be short, plain text strings (no sentences, no punctuation at the end).\n\n"
                "Output rules:\n"
                "- Respond ONLY with a JSON object and no explanation.\n"
                "- Do NOT include Japanese.\n"
                "- Do NOT include markdown, code fences, or comments.\n"
            )
        },
        {
            "role": "user",
            "content": f"Categorize and tag this idea:\n\n{raw_text}"
        }
    ]

    try:
        client, default_model = _get_client()
        use_model = model or default_model
        response = client.chat.completions.create(
            model=use_model,
            messages=messages,
            temperature=0.7
        )

        content = response.choices[0].message.content.strip()
        print("[DEBUG] Agent 1 raw response:", content)  # ★応答を表示
        
        # コードブロック（```json```など）を除去してからパース
        if content.startswith("```"):
            content = content.strip("`")  # まず ``` を削除
            parts = content.split("\n", 1)  # "json\n{...}" → ["json", "{...}"]
            if len(parts) == 2:
                content = parts[1].rsplit("```", 1)[0].strip()  # 最後の ``` も除去

        try:
            parsed = json.loads(content)
            category = parsed.get("category", "uncategorized")
            tags = parsed.get("tags", [])
        except Exception as e:
            print(f"[ERROR] Agent 1 categorization failed: {e}")
            print("[ERROR] Raw response was:", repr(response.choices[0].message.content))
            return "uncategorized", []

        print("\n=== Agent_1 受信メッセージ ===")
        print(response.choices[0].message)

        return category, tags
    
    except Exception as outer_e:  # ← これを追加
        print(f"[ERROR] Agent 1 failed during OpenAI call: {outer_e}")
        return "uncategorized", []
