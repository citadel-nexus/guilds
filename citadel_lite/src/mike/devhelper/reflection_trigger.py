# DevHelper: Reflection Trigger Core (Skeleton)
# このスケルトンは、"マイクが自分の応答を振り返るべきか？" を判断するための基盤です。

from datetime import datetime

class ReflectionTrigger:
    def __init__(self):
        self.last_trigger_time = None
        self.trigger_threshold = 5

    def evaluate(self, payload: dict) -> dict:
        """
        Payload入力に基づき、思考反射トリガー判定を行う。
        payload = {
            "metadata": {...},
            "flags": {...}
        }
        """
        metadata = payload.get("metadata", {})
        event_flags = payload.get("flags", {})

        vector_id = metadata.get("vector_id", "unknown")
        print(f"[ReflectionTrigger] evaluating... vector_id={vector_id}")

        score = 0
        reasons = []

        # ① 応答拒否
        if event_flags.get("rejection", False):
            score += 3
            reasons.append("rejection detected")

        # ② 信頼低下
        if metadata.get("trust", 1.0) < 0.5:
            score += 2
            reasons.append("trust below 0.5")

        # ③ 語彙の重複
        if metadata.get("repetition", 0.0) > 0.85:
            score += 2
            reasons.append("repetitive output pattern")

        # ④ ユーザーによる否定反応
        if event_flags.get("user_disconfirmed", False):
            score += 2
            reasons.append("user flagged response as inadequate")

        # ⑤ 感情トーンの急変
        if metadata.get("tone_shift", 0.0) > 0.6:
            score += 1
            reasons.append("emotional tone shifted sharply")

        # ⑥ 意図との背反
        if metadata.get("intent_drift", False):
            score += 2
            reasons.append("response does not align with purpose")

        # ⑦ 出力ギャップ（短すぎる・期待外れ）
        if metadata.get("expectation_gap", False):
            score += 3
            reasons.append("output failed to meet expected form/length")

        trigger = score >= self.trigger_threshold
        self.last_trigger_time = datetime.now() if trigger else self.last_trigger_time

        # === CAPS-style output ===
        return {
            "trigger": trigger,
            "score": score,
            "reason": reasons,
            "caps_directive": {
                "action": "reflect" if trigger else "store_caps",
                "intent_tag": "self_evaluation",
                "timestamp": datetime.now().isoformat()
            }
        }

# 使用例
# flags = {"rejection": True, "user_disconfirmed": False}
# meta = {"trust": 0.42, "repetition": 0.9, "tone_shift": 0.3, "expectation_gap": True}
# rt = ReflectionTrigger()
# print(rt.evaluate(flags, meta))