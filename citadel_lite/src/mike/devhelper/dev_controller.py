# DevHelper: Reflection Controller (Skeleton)
# マイクの応答処理後に、トリガー評価 → リフレクション発火 を制御するコントローラ


import os
import json
from datetime import datetime
from .reflection_trigger import ReflectionTrigger
from .reinject_handler import mark_for_reinjection
try:
    from config.config_loader import load_config
except (ImportError, ModuleNotFoundError):
    from src.mike.config.config_loader import load_config

config = load_config()

class DevController:
    def __init__(self, input_data):
        self.config = config  # 設定ファイルからのロード結果
        self.input_data = input_data
        self.trigger_core = ReflectionTrigger()

    def process(self):
        """
        仮の処理関数。今はinput_dataをそのまま返すだけ。
        本来はここでDevHelper本体の分析や加工をする予定。
        """
        return {"processed_input": self.input_data}


    def reflect(self, response_text, metadata, reflection_text=None):
        os.makedirs("logs", exist_ok=True)
        """
        実際の内省処理本体（スケルトン）
        - 応答テキストを分析し、改善案・再注入を生成
        - 現時点ではログ出力とマークダウン保存のみ
        """
        reflection_log = {
            "timestamp": datetime.now().isoformat(),
            "response": response_text,
            "insight": reflection_text or "Reflection pending: improvement path not yet implemented",
            "tags": metadata.get("reason", []),
            "vector_id": metadata.get("vector_id", "unknown")  # vector_idによりログトレース強化
        }

        # 保存先：reflection_logs.jsonl に追記
        if self.config.get("enable_reflection_logging", True):
            with open("logs/reflection_logs.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(reflection_log, ensure_ascii=False) + "\n")

        print("[DevHelper] Reflection recorded.")
        
    def run_post_response_diagnostics(self, event_flags, metadata, response_text, reflection=None):
        """
        応答完了後に呼び出され、リフレクショントリガーを評価し、必要なら反省処理や再注入処理を呼ぶ。
        """
        payload = {
            "flags": event_flags,
            "metadata": metadata
        }
        result = self.trigger_core.evaluate(payload)

        if result["trigger"]:
            reflection_text = reflection.get("reflection_text") if reflection else None
            print(f"[DevHelper] Reflection triggered. insight={reflection_text}")
            self.reflect(response_text, metadata, reflection_text=reflection_text)
        else:
            print("[DevHelper] No reflection needed.")

        # --- NEW: 信頼スコアによる再注入チェック ---
        if reflection:
            trust = reflection.get("trust_score", None)
            threshold = self.config.get("reinjection_trust_threshold", 0.5)
            if trust is not None and trust < threshold:
                print(f"[DevHelper] Low trust_score={trust:.2f} → marking for reinjection.")
                mark_for_reinjection(reflection_result=reflection, response_text=response_text, reason="low_trust_score")

# 使用例：
# controller = DevController()
# controller.run_post_response_diagnostics(event_flags, metadata, response_text)
