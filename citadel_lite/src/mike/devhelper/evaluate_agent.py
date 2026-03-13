#Evaluate_Agent
import openai
import os
import random
import re
import json

from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from .reflection_retry import re_reflect_if_needed

L0_SAVE_PATH = "data/metadata/L0/thought_metadata_L0.jsonl"

# 環境変数からAPIキー読み込み
load_dotenv()

# 利用可能な複数APIキー
OPENAI_KEYS = [
    os.getenv("OPENAI_API_KEY_1"),
    os.getenv("OPENAI_API_KEY_2"),
    os.getenv("OPENAI_API_KEY_3")
]
from ..engine.llm_client import get_llm_client
client, default_model = get_llm_client()

# --- 外部文脈を付加するためのラッパー関数 ---
def wrap_with_context(content, memory_text):
    return f"""【記憶】\n{memory_text}\n\n【評価対象】\n{content}"""


def ensure_dict(d):
    return d if isinstance(d, dict) else {}
    
def llm_evaluate(prompt, input_text, model=None):
    """LLM評価関数。modelが指定されなければデフォルトを利用"""
    use_model = model or default_model
    response = client.chat.completions.create(
        model=use_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": input_text}
        ],
        temperature=0.0,
        max_tokens=300,
        n=1,
        stop=None
    )

    content = response.choices[0].message.content.strip()

    # 正規表現でスコアと理由を抽出
    score_match = re.search(r"スコア:\s*([\d\.]+)", content)
    reason_match = re.search(r"理由:\s*(.+)", content, re.DOTALL)

    score = float(score_match.group(1)) if score_match else 0.0
    reason = reason_match.group(1).strip() if reason_match else "評価理由の取得に失敗しました。"

    return {
        "score": max(min(score, 1.0), 0.0),
        "reason": reason
    }

# L0保存関数
def save_thought_with_regeneration_to_L0(vector_id, original_text, original_scores, original_score, regenerated_text, regenerated_scores, regenerated_score, human_thought_comment=None ):
    record = {
        "vector_id": vector_id,
        "timestamp": datetime.now().isoformat(),
        "used_in_response": False,
        "original": {
            "thought_text": original_text,
            "evaluation_score": original_score,
            "scores": {
                k: round(v["score"], 2) for k, v in (original_scores or {}).items()
            },
            "reason_summary": {
                k: v["reason"] for k, v in (original_scores or {}).items()
            }
        },
        "regenerated": {
            "thought_text": regenerated_text,
            "evaluation_score": regenerated_score,
            "regenerated_scores": {
                k: round(v.get("score", 0), 2) for k, v in ensure_dict(regenerated_scores).items()
            },
            "reason_summary": {
                k: v.get("reason", "") for k, v in ensure_dict(regenerated_scores).items()
            }
        }
    }
    if human_thought_comment:
        record["human_thought_comment"] = human_thought_comment
        
    with open(L0_SAVE_PATH, mode="a", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
        f.write("\n")

# 再評価の組み込み
def evaluate_reflection(refined_text, run_agent_3_fn, threshold=0.5, vector_id=None):

    """
    Agent 3 による反省評価を実行し、閾値を下回る場合には re_reflect を試みる。
    trust_score による再注入判断は dev_controller 側に委ねる。
    """
    reflection = run_agent_3_fn(refined_text)
    reflection["vector_id"] = vector_id  # ← ここで安全に代入
    reflection = re_reflect_if_needed(
        reflection=reflection,
        refined_text=refined_text,
        run_agent_3_fn=run_agent_3_fn,
        threshold=threshold,
    )
    return reflection  # trust_score, reflection_score を含んでいればOK

# 思考評価Agentのクラス (LLMベース版)
class ThoughtEvaluationAgent:
    def __init__(self):
        self.prompts = {
            "Logical Consistency": (
                "以下の推論が「観測可能な事実から導かれておらず論理的に破綻している」場合は0.0、"
                "「観測可能な事実から導かれているがその事実が正確性に乏しい」場合は0.2、"
                "「観測可能な事実から導かれており概ね論理的だが完全ではない」場合は0.4、"
                "「観測可能な事実から導かれていないがそのことを提示している」場合は0.6、"
                "「信頼できる観測可能な事実から導かれており完全に論理的で矛盾がない」場合のみ1.0を返してください。"
                "主観的な忖度はせず厳しく評価してください。"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明>"
            ),

            "Reasoning Validity": (
                "次の推論において、根拠や理由が明確で十分かを評価します。"
                "「ユーザの要求にこたえるための根拠が全くない」場合は0.0、"
                "「ユーザの要求にこたえるための根拠が乏しく説得力に欠ける」場合は0.2、"
                "「ユーザの要求にこたえるための根拠はあるが説明が不足している」場合は0.4、"
                "「ユーザの要求にこたえるための根拠がないが根拠がないと明示している」場合は0.6、"
                "「ユーザの要求にこたえるための根拠が明確で十分な説得力がある」場合のみ1.0を返してください。"
                "この観点は特に客観的に厳密に評価してください。"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明>"
            ),

            "Clarity": (
                "以下の推論が明瞭で理解しやすいかを評価します。"
                "「全く理解できない」なら0.0、"
                "「分かりにくい部分が多い」なら0.2、"
                "「概ね分かりやすいが一部曖昧」なら0.4、"
                "「非常に明確で完全に理解可能」なら1.0を返してください。"
                "客観的に評価してください。"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明>"
            ),

            "Trust Score": (
                "次の推論全体の信頼性を評価してください。"
                "「根拠も推論もまったく信頼できない」場合は0.0、"
                "「根拠が信頼できないため、推論を信頼するには不安が残る」場合は0.2、"
                "「根拠が部分的に信頼できるが推論を信頼するに完全ではない」場合は0.4、"
                "「根拠が信頼できないが、その信頼できない点を明示したうえで推論している」場合は0.6、"
                "「根拠も推論も完全に信頼できる」場合のみ1.0を返してください。"
                "忖度せず客観的に厳密に評価してください。"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明>"
            )
        }

    def evaluate(self, response, memory_text=""):
        scores = {}
        print(" ThoughtEvaluationAgent (LLM) is evaluating...")
        wrapped_response = wrap_with_context(response, memory_text)
        for criterion, prompt in self.prompts.items():
            scores[criterion] = llm_evaluate(prompt, wrapped_response)

        overall_score = round(sum(detail["score"] for detail in scores.values()) / len(scores), 2)

        for criterion, detail in scores.items():
            print(f"{criterion}: {detail['score']}（理由: {detail['reason']}）")
#        print(f"Overall Response Evaluation Score: {overall_score}\n")
        return scores, overall_score

# 応答評価Agentのクラス (LLMベース版)
class ResponseEvaluationAgent:
    def __init__(self):
        self.prompts = {
            "Accuracy": (
                "次の応答がユーザーの要求に正確に応えているかを評価してください。\n"
                "具体的には、以下の基準に従って厳密にスコアをつけてください。\n"
                "- スコア 0.0: ユーザーの要求の主題に対して全く答えていない、または論点がずれている。\n"
                "- スコア 0.2: 主題に関係しているが、回答が漠然としており具体性に欠ける。\n"
                "- スコア 0.4: 主題への回答はあるが重要な要素が欠けている、または回答が部分的に曖昧。\n"
                "- スコア 0.6: 主題にほぼ答えているが、一部の具体的情報や理由説明が不十分。\n"
                "- スコア 0.8: 質問内容が明瞭で、短い回答で十分と判断でき、質問の内容に回答が合致している場合。\n"
                "- スコア 1.0: 主題に完全かつ具体的に答えており、要求を満たせなかった場合は理由を明確に提示している。\n"
                "必ず具体的な例を挙げて評価理由を説明してください。客観的かつ厳密に評価し、絶対に忖度をしないでください。\n"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明（具体例を含む）>"
            ),
                        
            "User Experience": (
                "次の応答がユーザーにとって読みやすく、情報が適切に整理されているかを評価します。\n"
                "- スコア 0.0: 非常に読みづらく、情報が乱雑でユーザーが混乱する。\n"
                "- スコア 0.2: 一部読みやすいが情報の順序や整理に問題がある。\n"
                "- スコア 0.4: 概ね読みやすいが、一部情報提示の順序や明確さに改善が必要。\n"
                "- スコア 0.6: 読みやすく、情報配置も適切だが、根拠や具体例がやや不足。\n"
                "- スコア 0.8: ユーザー入力の意図に対して適切な構成である。\n"
                "- スコア 1.0: 非常に読みやすく、情報の順序、整理、根拠提示が完璧でユーザーに優しい。\n"
                "必ず具体的な例を挙げて評価理由を説明してください。\n"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明（具体例を含む）>"
            ),
            
            "Tone Appropriateness": (
                "次の応答のトーンや感情表現がユーザーの要求と文脈に適切かを評価します。\n"
                "- スコア 0.0: トーンが著しく不適切で違和感が非常に強い。\n"
                "- スコア 0.3: 部分的に不適切な表現があり、ユーザーに不快感や違和感を与える可能性がある。\n"
                "- スコア 0.6: 概ね適切だが、一部に若干の違和感や調整が必要。\n"
                "- スコア 1.0: 完全に適切で自然であり、ユーザーの要求や文脈に完璧に調和している。\n"
                "具体的にどの表現が適切または不適切かを明示してください。\n"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明（具体例を含む）>"
            ),
            
            "Contextual Integrity": (
                "次の応答が前後の文脈に完全に適合しているかを評価してください。\n"
                "- スコア 0.0: 文脈から完全に逸脱しており、全く関連性がない。\n"
                "- スコア 0.3: 一部の内容が文脈と乖離しており、不自然な印象を与える。\n"
                "- スコア 0.6: 概ね文脈に適合しているが、細かな部分に若干の違和感がある。\n"
                "- スコア 1.0: 前後の文脈に完全に自然に適合しており、一切の違和感がない。\n"
                "具体的にどの部分が適合または逸脱しているかを指摘してください。\n"
                "客観的かつ厳密に評価し、絶対に忖度をしないでください。\n"
                "【返却形式】\n"
                "スコア: <数値>\n"
                "理由: <評価理由の説明（具体例を含む）>"
            )
        }

    def evaluate(self, response, memory_text=""):
        scores = {}
        print(" ResponseEvaluationAgent (LLM) is evaluating...")
        wrapped_response = wrap_with_context(response, memory_text)
        for criterion, prompt in self.prompts.items():
            scores[criterion] = llm_evaluate(prompt, wrapped_response)

        overall_score = round(sum(detail["score"] for detail in scores.values()) / len(scores), 2)

        for criterion, detail in scores.items():
            print(f"{criterion}: {detail['score']}（理由: {detail['reason']}）")
#        print(f"Overall Response Evaluation Score: {overall_score}\n")
        return scores, overall_score
        
        if vector_id:
            save_thought_to_L0(vector_id, response, scores, overall_score)
