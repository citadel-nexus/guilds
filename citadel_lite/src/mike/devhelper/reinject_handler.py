# devhelper/reinject_handler.py

import os
from datetime import datetime

# シンプルな再注入ログ保存処理（将来的にはDBやキュー処理に移行可）
def mark_for_reinjection(reflection_result, response_text, reason="low_score"):
    print(f"[Reinject] Reinjection marked for vector_id={reflection_result.get('vector_id', 'unknown')}")
    """
    指定された応答を再注入対象としてログに記録する。
    """
    reinject_log = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "vector_id": reflection_result.get("vector_id", "unknown"),
        "reflection_score": reflection_result.get("reflection_score", None),
        "trust_score": reflection_result.get("trust_score", None),
        "response": response_text,
        "re_reflected": reflection_result.get("re_reflected", False)
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/reinject_queue.jsonl", "a", encoding="utf-8") as f:
        f.write(str(reinject_log) + "\n")

    print(f"[Reinject] Entry logged for reinjection (reason: {reason})")
    return reinject_log
