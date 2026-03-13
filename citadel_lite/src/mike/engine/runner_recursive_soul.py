# runner_recursive_soul_r2.py
# import安全＋main実行時のみバッチ＋run_recursive_soul(record)単体呼び出し対応

import sys
import os
import uuid
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import numpy as np
try:
    from langdetect import detect as _detect_lang
except ImportError:
    def _detect_lang(text: str) -> str:  # type: ignore[misc]
        """Fallback when langdetect is not installed — assumes English."""
        return "en"
detect = _detect_lang

from ..config.config_loader import load_config
from .agent_1_categorize import run_agent_1
from .agent_2_elaborate import run_agent_2
from .agent_3_reflector import run_agent_3
from .metadata_writer import save_vector_metadata
from .index_builder import register_entry
from .embedding_tools import get_embedding
from .utils import hash_text, load_previous_hashes, save_hashes
from ..devhelper.dev_controller import DevController
from .llm_client import get_llm_client

# NOTE:
#   Blueprint用のユーティリティ (bp_ingest_and_search_r1) は
#   run_recursive_soul(record) には不要。
#   ingest_blueprints_via_agents(...) を呼ぶときにだけ遅延importする。

config = load_config()
BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_PATH = BASE_DIR / config["input_path"]
HASH_CACHE_PATH = BASE_DIR / config["hash_cache_path"]
BOOK_VECTOR_PATH = BASE_DIR / config["book_vector_path"]
SCHEMA_PATH = BASE_DIR / config["schema_path"]



with open(SCHEMA_PATH, encoding="utf-8") as f:
    default_dict = json.load(f)

def now_ts():
    return datetime.now(timezone.utc).isoformat()

def detect_language(text):
    try:
        return detect(text)
    except Exception:
        return "unknown"
prev_hashes = load_previous_hashes(HASH_CACHE_PATH)
curr_hashes = {}

### Intentベースのアクション分類器

def determine_caps_directive(intent: str) -> dict:
    if intent.lower() in {"reconnect", "context_switch", "greeting"}:
        return {"action": "discard", "intent_tag": intent}
    elif intent.lower() in {"reflect", "analyze", "learn"}:
        return {"action": "store_caps", "intent_tag": intent}
    elif intent.lower() in {"escalate", "zayara_push"}:
        return {"action": "store_zayara", "intent_tag": intent}
    return {"action": "store_caps", "intent_tag": intent}
    
    
    
def fill_none_with_default(packet, default_dict):
    result = packet.copy()
    for k, v in default_dict.items():
        if k not in result or result[k] is None:
            result[k] = v
    return result

def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _extract_context(handoff: Dict[str, Any], decision: Dict[str, Any], verify: Dict[str, Any]) -> Dict[str, Any]:
    agent_outputs = (handoff.get("agent_outputs") or {})
    sherlock = agent_outputs.get("sherlock", {})
    fixer = agent_outputs.get("fixer", {})
    guardian = agent_outputs.get("guardian", {})
    verify_results = verify.get("results") or []
    return {
        "event": handoff.get("event") or {},
        "sherlock": sherlock,
        "fixer": fixer,
        "guardian": guardian,
        "decision": decision or {},
        "verify": {
            "all_success": bool(verify.get("all_success")),
            "simulated": bool(verify.get("simulated")),
            "results": verify_results[:6],
        },
    }

def generate_mike_review(
    *,
    handoff_path: Path,
    decision_path: Path,
    verify_path: Path,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    handoff = _read_json(handoff_path)
    decision = _read_json(decision_path)
    verify = _read_json(verify_path)

    ctx = _extract_context(handoff, decision, verify)
    event = ctx.get("event") or {}
    event_id = event.get("event_id") or decision.get("event_id") or ""

    client, default_model = get_llm_client()
    system = (
        "You are Mike, a Meta-Agent and Quality Reviewer for an agentic DevOps pipeline. "
        "Review the outputs from Sherlock/Fixer/Guardian and the verify results. "
        "Return ONLY a JSON object with fields: "
        "verdict, issues, recommendations, recheck, confidence, review_text."
    )
    user = json.dumps(ctx, ensure_ascii=False)

    review: Dict[str, Any] = {}
    try:
        resp = client.chat.completions.create(
            model=default_model,
            temperature=0.3,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            parts = content.split("\n", 1)
            if len(parts) == 2:
                content = parts[1].rsplit("```", 1)[0].strip()
        review = json.loads(content)
    except Exception:
        review = {}

    if not isinstance(review, dict) or not review:
        # Deterministic fallback
        verify_all = bool(verify.get("all_success")) if verify else False
        action = decision.get("action", "unknown") if isinstance(decision, dict) else "unknown"
        review = {
            "verdict": "recheck" if not verify_all else "approve",
            "issues": [] if verify_all else ["verify_failed_or_missing"],
            "recommendations": [
                "Inspect verify_results and adjust fix plan",
                "Add minimal regression test or verification step",
            ] if not verify_all else ["Proceed with monitored rollout"],
            "recheck": not verify_all,
            "confidence": 0.4,
            "review_text": (
                f"Decision={action}, verify_all_success={verify_all}. "
                "Fallback review generated without LLM."
            ),
        }

    review.update({
        "event_id": event_id,
        "generated_at": now_ts(),
    })

    out_path = output_path or (handoff_path.parent / "mike_review.json")
    _write_json(out_path, review)
    return review

def run_mike_review_and_remember(
    *,
    handoff_path: Path,
    decision_path: Path,
    verify_path: Path,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    review = generate_mike_review(
        handoff_path=handoff_path,
        decision_path=decision_path,
        verify_path=verify_path,
        output_path=output_path,
    )

    # Remember this review as a new memory entry
    try:
        record = {
            "input_text": f"[MIKE_REVIEW] event_id={review.get('event_id','')}",
            "response_text": review.get("review_text", ""),
            "refined_text": review.get("review_text", ""),
            "source": "mike_review",
            "thread_title": review.get("event_id") or "mike_review",
        }
        _ = run_recursive_soul(record)
    except Exception:
        pass

    return review

def run_recursive_soul(record):
    """
    1件のdict（input_text, response_text などを持つ）をAgent評価・メタ生成し、metadata(dict)を返す
    """
    input_text = record.get("input_text", "").strip()
    response_text = record.get("response_text", "").strip()
    refined_text = record.get("refined_text", "").strip() if "refined_text" in record else response_text
    source = (record.get("source") or "recursive_soul").strip() or "recursive_soul"
    thread_title = record.get("thread_title") or "cli_mike"

    if not refined_text and not response_text:
        print(f"{now_ts()} [SKIP] Empty refined_text and response_text")
        print(f"[SKIP理由] input_text={record.get('input_text')!r}, response_text={record.get('response_text')!r}, refined_text={record.get('refined_text')!r}")
        return None




    # --- Agent 1 ---
    try:
        category, agent_tags = run_agent_1(refined_text, model="gpt-4o-mini")
    except Exception as e:
        print(f"{now_ts()} ❌ Agent_1 failed: {e}")
        return None

    # --- Agent 2 ---
    try:
        enrichment = run_agent_2(refined_text, model="gpt-4o-mini")
    except Exception as e:
        print(f"{now_ts()} ❌ Agent_2 failed: {e}")
        return None

    # --- Agent 3 ---
    try:
        reflection = run_agent_3(enrichment["refined_text"], model="gpt-4o-mini")
    except Exception as e:
        print(f"{now_ts()} ❌ Agent_3 failed: {e}")
        return None

    try:
        score = float(reflection.get("reflection_score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    threshold = config.get("reflection_recheck_threshold", 0.5)
    

    if score < threshold:
        try:
            reflection = run_agent_3(enrichment["refined_text"], model="gpt-4o-mini")
            reflection["re_reflected"] = True
        except Exception as e:
            print(f"{now_ts()} ❌ Agent_3 retry failed: {e}")
            return None
    else:
        reflection["re_reflected"] = False



    # CLI Mike用スレッドタイトルの扱い
    origin_file = thread_title
        
    # 必須フィールドにデフォルト値をセット
    for k, v in {
        "clarity_score": float(reflection.get("clarity_score", 0.0) or 0),
        "human_echo_score": float(reflection.get("human_echo_score", 0.0) or 0),
        "insight_score": float(reflection.get("insight_score", 0.0) or 0), 
        "logic_quality_score": float(reflection.get("logic_quality_score", 0.0) or 0), 
        "self_rating": float(reflection.get("self_rating", 0.0) or 0), 
        "reflection_score": float(reflection.get("reflection_score", 0.0) or 0), 
        "trust_score": float(reflection.get("trust_score", 0.0) or 0), 
        "origin_file": origin_file,
        "status": "", "tier": "",
        "parent_vector": "", "child_vectors": [], "recursive_cycles": 0,
        "recursive_evolution_count": 0, "refinement_loop_triggered": False
    }.items():
        reflection.setdefault(k, v)

    controller = DevController(input_data=input_text)
    controller.run_post_response_diagnostics(
        event_flags={},
        metadata={"trust": reflection.get("trust_score", 0.0)},
        response_text=enrichment["refined_text"],
        reflection=reflection
    )


            
    # Agent処理成功後、packet生成直前にvector_idを作成
    vector_id = f"soul_{uuid.uuid4().hex[:8]}"
    composite = "\n".join([input_text, response_text, enrichment["refined_text"]])
    line_hash = hash_text(composite)
    curr_hashes[vector_id] = line_hash
    
    # --- timestamp 正規化（保存はUTC、表示用にJSTも持つならここで） ---
    jst = timezone(timedelta(hours=9))
    packet_timestamp_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    packet_timestamp_jst = datetime.now(jst).isoformat()

    # reflection の timestamp は退避（古い年が混ざるのを防ぐ）
    if isinstance(reflection, dict) and "timestamp" in reflection:
        reflection["source_timestamp"] = reflection.pop("timestamp")

    # --- メタデータパケット生成 ---
    packet = {
        "vector_id": vector_id,
        "input_text": input_text,
        "response_text": response_text,
        "refined_text": enrichment["refined_text"],
        "reflection_text": reflection.get("reflection_text", ""),
        "language": detect_language(input_text or enrichment["refined_text"]),
        "category": category,
        "tags": list(dict.fromkeys(["soul", "recursive"] + (agent_tags or []) + [category])),
        "recursive_level": 3,
        "lineage": reflection.get("lineage", ""),
        "clarity_score": reflection.get("clarity_score", 0.0),
        "human_echo_score": reflection.get("human_echo_score", 0.0),
        "insight_score": reflection.get("insight_score", 0.0),
        "logic_quality_score": reflection.get("logic_quality_score", 0.0),
        "self_rating": reflection.get("self_rating", 0.0),
        "reflection_score": reflection.get("reflection_score", 0.0),
        "trust_score": reflection.get("trust_score", 0.0),
        "origin_file": origin_file,
        "status": reflection.get("status", ""),
        "tier": reflection.get("tier", ""),
        "parent_vector": reflection.get("parent_vector", ""),
        "child_vectors": reflection.get("child_vectors", []),
        "recursive_cycles": reflection.get("recursive_cycles", 0),
        "recursive_evolution_count": reflection.get("recursive_evolution_count", 0),
        "refinement_loop_triggered": reflection.get("refinement_loop_triggered", False),
        "intent": reflection.get("primary_intent", ""),
        "system_notes": "recursive_soul_pipeline",
        "timestamp": packet_timestamp_utc,
        "timestamp_jst": packet_timestamp_jst,  # 任意（表示用）
        "source": source,
    }

    # --- Payload構築 ---
    payload = {
        "caps_directive": determine_caps_directive(packet["intent"]),
        "caps_metadata": {
            "vector_id": packet["vector_id"],
            "input_text": packet["input_text"],
            "response_text": packet["response_text"],
            "refined_text": packet["refined_text"],
            "language": packet["language"],
            "category": packet["category"],
            "tags": packet["tags"],
            "origin_file": packet["origin_file"],
            "status": packet["status"],
            "parent_vector": packet["parent_vector"],
            "child_vectors": packet["child_vectors"],
            "system_notes": packet["system_notes"],
            "source": packet.get("source", "recursive_soul"),
            "timestamp": packet["timestamp"],
            "recursive_cycles": packet["recursive_cycles"],
            "recursive_evolution_count": packet["recursive_evolution_count"],
            "refinement_loop_triggered": packet["refinement_loop_triggered"]
        },
        "evaluation_scores": {
            "clarity_score": packet["clarity_score"],
            "human_echo_score": packet["human_echo_score"],
            "insight_score": packet["insight_score"],
            "logic_quality_score": packet["logic_quality_score"],
            "self_rating": packet["self_rating"],
            "reflection_score": packet["reflection_score"],
            "trust_score": packet["trust_score"]
        },
    }

    # ---- 埋め込みは input/response/refined の結合で作る ----
    def _safe_concat(*parts, maxlen=4000):
        joined = "\n".join([p for p in parts if isinstance(p, str) and p.strip()])
        return joined[:maxlen]
    text_for_embedding = _safe_concat(
        packet.get("input_text", ""),
        packet.get("response_text", ""),
        packet.get("refined_text", "")
    )


    try:
        vec = get_embedding(text_for_embedding)
    except Exception as e:
        print(f"{now_ts()} ❌ 埋め込み生成に失敗: {e}")
        return None

    res_vec = np.array(vec, dtype="float32")
    if res_vec.ndim == 1:
        res_vec = res_vec.reshape(1, -1)

    # index_builder は (payload, resonance_vector) を期待
    vector_id_saved = register_entry(payload, res_vec)
    if not vector_id_saved:
        print(f"{now_ts()} [WARN] register_entry がスキップ/失敗（vector_id={packet['vector_id']}）")
    return packet
# ============================================================
# BLUEPRINT → (全エージェント) → register_entry
#   * 会話記憶と“完全に同じ”経路で保存する
#   * 1) ファイル→チャンク化 2) 各チャンクを record 化
#   * 3) run_recursive_soul(record) を通す 4) refined_text で埋め込み→register_entry
#   * 5) 親子リンク（ファイル=親, チャンク=子）を付与
# ============================================================
def ingest_blueprints_via_agents(
    root: str,
    glob_pattern: str = "*.md;*.taskir.*;*.json",
    project: str = "ZCES",
    tags: List[str] | None = None,
    chunk_tokens: int = 800,
    overlap: int = 120,
) -> None:
    # ★ ここでだけ bp_ingest_and_search_r1 を import（遅延）
    try:
        from bp_ingest_and_search_r1 import TokenCounter, smart_md_chunks, iter_files, read_text_auto
    except Exception as e:
        raise ImportError(
            f"ingest_blueprints_via_agents requires bp_ingest_and_search_r1, but import failed: {e}"
        )
    tags = tags or ["blueprint"]
    counter = TokenCounter()
    root_path = Path(root)
    globs = [g.strip() for g in glob_pattern.split(";") if g.strip()]
    files = [p for p in iter_files(root_path, globs) if p.is_file()]

    for p in files:
        rel = str(p.relative_to(root_path))
        try:
            text = read_text_auto(p)
        except Exception as e:
            print(f"{now_ts()} [WARN] 読み込み失敗: {rel}: {e}")
            continue

        base_meta = {"project": project, "tags": tags, "kind": "blueprint", "origin_file": rel}
        chunks = smart_md_chunks(
            text=text,
            relpath=rel,
            counter=counter,
            chunk_tokens=chunk_tokens,
            overlap=overlap,
            base_meta=base_meta,
        )

        # ---------- 親（ファイル単位）を先に作る ----------
        parent_vector_id = f"bp_parent_{hash_text(rel)[:12]}"
        parent_payload = {
            "caps_directive": {"action": "store_caps", "intent_tag": "ingest_blueprint_parent"},
            "caps_metadata": {
                "vector_id": parent_vector_id,
                "input_text": f"[BLUEPRINT] {rel}",
                "response_text": "",
                "refined_text": f"FILE:{rel}\nPROJECT:{project}\nTAGS:{','.join(tags)}",
                "language": "unknown",
                "category": "blueprint",
                "tags": list(dict.fromkeys(tags + ["blueprint", project])),
                "origin_file": rel,
                "status": "",
                "parent_vector": "",
                "child_vectors": [],
                "system_notes": "blueprint_parent_via_agents",
                "source": "blueprint",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "recursive_cycles": 0,
                "recursive_evolution_count": 0,
                "refinement_loop_triggered": False,
            },
            "evaluation_scores": {
                "clarity_score": 0.0, "human_echo_score": 0.0, "insight_score": 0.0,
                "logic_quality_score": 0.0, "self_rating": 0.0, "reflection_score": 0.0, "trust_score": 0.0,
            },
        }
        # 親は軽量ベクトル（ファイル説明ベクトル）でOK
        try:
            vec_p = get_embedding(parent_payload["caps_metadata"]["refined_text"])
            np_vec_p = np.array(vec_p, dtype="float32").reshape(1, -1)
            _ = register_entry(parent_payload, np_vec_p)
        except Exception as e:
            print(f"{now_ts()} [PARENT-EMBED❌] {rel} :: {e}")
            # 親が無くても子は継続

        # ---------- 子（チャンク）を全エージェントに通す ----------
        child_ids: List[str] = []
        for ch in chunks:
            # 会話パイプライン互換のレコードに整形
            record = {
                # input/response に最低限入れておくとエージェント達が素直に動く
                "input_text": f"[BP:{rel}] {ch.section}",
                "response_text": ch.text,
                # 既に refined_text を持つ前提の設計がある場合でも run_recursive_soul が埋めるのでOK
                "origin_file": ch.relpath,
                "project": project,
                "tags": list(dict.fromkeys(tags + ["blueprint", project])),
                "category": "blueprint",
                "source": "blueprint",
            }

            # 1) 全エージェント通過 → packet 生成（会話記憶と同じ）
            try:
                packet: Dict[str, Any] = run_recursive_soul(record)
            except Exception as e:
                print(f"{now_ts()} [AGENTS❌] {rel} / {ch.chunk_id} :: {e}")
                continue

            # 2) メタ補強（origin, parent, section など）
            cm = dict(packet.get("caps_metadata", {}) or {})
            cm["vector_id"]      = cm.get("vector_id") or f"bp_{hash_text(ch.chunk_id)[:12]}"
            cm["origin_file"]    = rel
            cm["section"]        = ch.section
            cm["parent_vector"]  = parent_vector_id
            cm["category"]       = "blueprint"
            cm["tags"]           = list(dict.fromkeys((cm.get("tags") or []) + ["blueprint", project] + tags))

            # 2.5) refined_text を必ず埋める（空なら response_text → 最後に ch.text）
            rt = (cm.get("refined_text") or packet.get("response_text") or ch.text or "").strip()
            cm["refined_text"] = rt
            packet["caps_metadata"] = cm

            # refined_text が本当に空なら、このチャンクは安全にスキップ（ログのみ）
            if not rt:
                print(f"{now_ts()} [INGEST-BP⚠]  refined_text empty -> SKIP {rel} :: chunk_id={ch.chunk_id}")
                continue

            # 3) ベクトル生成（会話記憶と同等：refined_text をベースに）
            base_text = rt

            try:
                vec = get_embedding(base_text)
            except Exception as e:
                print(f"{now_ts()} [EMBED❌] {rel} / {ch.chunk_id} :: {e}")
                continue

            np_vec = np.array(vec, dtype="float32")
            if np_vec.ndim == 1:
                np_vec = np_vec.reshape(1, -1)

            saved_id = register_entry(packet, np_vec)
            if saved_id:
                child_ids.append(cm["vector_id"])
                print(f"{now_ts()} [INGEST-BP✅] {rel} :: section='{ch.section}' :: chunk_id={ch.chunk_id}")
            else:
                print(f"{now_ts()} [INGEST-BP⚠]  SKIP/FAIL {rel} :: chunk_id={ch.chunk_id}")

        # ---------- 親に子リンクを反映（任意・対応していれば） ----------
        try:
            if child_ids:
                parent_payload["caps_metadata"]["child_vectors"] = child_ids
                # 親を更新（register_entry が upsert なら二度目で子リンクが入る）
                vec_p2 = get_embedding(parent_payload["caps_metadata"]["refined_text"])
                np_vec_p2 = np.array(vec_p2, dtype="float32").reshape(1, -1)
                _ = register_entry(parent_payload, np_vec_p2)
        except Exception as e:
            print(f"{now_ts()} [PARENT-UPDATE⚠] {rel} :: {e}")
# ========== mainバッチ処理はここだけ ==============
def main():
    # 既存の一括処理（標準入力/ファイル）を回したいときのために残す
    # UIやDiscordからの単発呼び出しでは使わない
    pass
    
if __name__ == "__main__":
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"INPUT_PATH: {INPUT_PATH}")
    print(f"BOOK_VECTOR_PATH: {BOOK_VECTOR_PATH}")
    print(f"SCHEMA_PATH: {SCHEMA_PATH}")
    print(f"{now_ts()} [INFO] Loaded INPUT from: {INPUT_PATH}")
    print(f"{now_ts()} [INFO] Will write vectors to: {BOOK_VECTOR_PATH}")

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            try:
                record = json.loads(line)
            except Exception:
                print(f"{now_ts()} [SKIP] Invalid JSON on line {line_no}: {line[:40]}")
                continue

            input_text = record.get("input_text", "").strip()
            line_hash = hash_text(input_text)

            if line_hash in prev_hashes.values():
                print(f"{now_ts()} [SKIP] 重複データ（既出ハッシュ）: {line_hash}")
                continue

            packet = run_recursive_soul(record)
            if packet:
                curr_hashes[packet["vector_id"]] = line_hash

    save_hashes(curr_hashes, HASH_CACHE_PATH)
    print(f"{now_ts()} [INFO] ハッシュをキャッシュに保存完了: {HASH_CACHE_PATH}")
    print(f"{now_ts()} [INFO] 全処理完了")
