# engine/index_builder.py
from __future__ import annotations

import json
import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:
    import faiss  # type: ignore
except Exception as e:
    raise RuntimeError(f"[index_builder] faiss の読み込みに失敗しました: {e}")

# =============================================================================
# 設定ロード
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline_config.json"

def load_config() -> Dict[str, Any]:
    # 既存の loader があれば優先
    try:
        try:
            from config.config_loader import load_config as _lc  # type: ignore
        except (ImportError, ModuleNotFoundError):
            from src.mike.config.config_loader import load_config as _lc
        cfg = _lc()
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    # フォールバック: JSON直読み
    if DEFAULT_CONFIG_PATH.exists():
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # 最小デフォルト
    return {
        "caps_faiss_path": "index/caps/index_caps.faiss",
        "caps_registry_jsonl": "index/caps/index_caps.jsonl",
        "hash_cache_path": "data/cache/hashes.json",
    }

CFG = load_config()

def _abs_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (PROJECT_ROOT / path)

CAPS_FAISS_PATH: Path = _abs_path(CFG.get("caps_faiss_path", "index/caps/index_caps.faiss"))
CAPS_META_PATH: Path  = _abs_path(CFG.get("caps_registry_jsonl", "index/caps/index_caps.jsonl"))
HASH_CACHE_PATH: Path = _abs_path(CFG.get("hash_cache_path", "data/cache/hashes.json"))

CAPS_META_PATH.parent.mkdir(parents=True, exist_ok=True)
HASH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
if not HASH_CACHE_PATH.exists():
    HASH_CACHE_PATH.write_text("{}", encoding="utf-8")
CAPS_FAISS_PATH.parent.mkdir(parents=True, exist_ok=True)  # ★ 追加：FAISS格納先も作成

# =============================================================================
# FAISS ユーティリティ
# =============================================================================

def _load_or_create_index(dimension: int) -> Any:
    """
    既存インデックスを読み込む。なければ L2 の Flat index を作成。
    """
    if CAPS_FAISS_PATH.exists():
        try:
            index = faiss.read_index(str(CAPS_FAISS_PATH))
            # ★ 既存インデックスの次元と新規ベクトル次元を照合
            if hasattr(index, "d") and index.d != dimension:
                raise RuntimeError(
                    f"[index_builder] 既存indexの次元({index.d})とベクトル次元({dimension})が不一致です。"
                )
            return index
        except Exception as e:
            raise RuntimeError(f"[index_builder] 既存インデックスの読み込みに失敗: {e}")

    # 新規作成（L2）
    try:
        index = faiss.IndexFlatL2(dimension)
        faiss.write_index(index, str(CAPS_FAISS_PATH))  # プレースホルダ保存（権限確認用）
        return index
    except Exception as e:
        raise RuntimeError(f"[index_builder] インデックス新規作成に失敗: {e}")


def _append_to_index(vector: np.ndarray) -> int:
    """
    ベクトルを追加して、追加後のインデックスサイズ-1（=新規ID相当）を返す。
    """
    if vector.ndim != 2:
        raise ValueError("[index_builder] vector は shape=(1, d) の2次元で渡してください")
    d = vector.shape[1]
    index = _load_or_create_index(d)
    try:
        index.add(vector.astype("float32"))
        faiss.write_index(index, str(CAPS_FAISS_PATH))
        return index.ntotal - 1
    except Exception as e:
        raise RuntimeError(f"[index_builder] インデックスへの追加に失敗: {e}")


# =============================================================================
# メタJSONLユーティリティ
# =============================================================================

def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _load_hash_cache() -> Dict[str, str]:
    try:
        with open(HASH_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_hash_cache(cache: Dict[str, str]) -> None:
    with open(HASH_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def _ensure_refined_text(metadata: Dict[str, Any]) -> str:
    """
    refined_text が空/未定義なら response_text → input_text → "" の順で補完。
    戻り値は確定した refined_text。
    """
    rt = metadata.get("refined_text")
    if not isinstance(rt, str) or not rt.strip():
        rt = metadata.get("response_text") or metadata.get("input_text") or ""
        metadata["refined_text"] = rt
    return rt

def _build_flat_meta(
    vector_id: str,
    payload: Dict[str, Any],
    metadata: Dict[str, Any],
    scores: Dict[str, Any],
    *,
    faiss_id: Optional[int] = None,
    embed_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    検索系が扱いやすい“フラット形”のメタを組み立てる。
    - refined_text / input_text / response_text / language / category / tags / vector_id をトップに
    - 監査用として caps_directive / evaluation_scores をネスト保存
    """
    refined_text = _ensure_refined_text(metadata)

    flat = {
        "vector_id": vector_id,
        "faiss_id": faiss_id,                # ★ 追記
        "refined_text": refined_text,
        "response_text": metadata.get("response_text", ""),
        "input_text": metadata.get("input_text", ""),
        "language": metadata.get("language", ""),
        "category": metadata.get("category", ""),
        "tags": metadata.get("tags", []),
        "created_at": _utc_now_iso_z(),
        "embed_version": embed_version or metadata.get("embed_version", ""),  # ★ 任意
        # 任意で残したい情報はネストでOK
        "caps_directive": payload.get("caps_directive", {}),
        "evaluation_scores": scores,
    }
    # tags が文字列になっているケースを吸収
    if not isinstance(flat["tags"], list):
        flat["tags"] = [str(flat["tags"])]
    return flat

def _write_meta_jsonl(flat_meta: Dict[str, Any]) -> None:
    with open(CAPS_META_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(flat_meta, ensure_ascii=False) + "\n")


# =============================================================================
# 重複判定（複合スニペットのハッシュ）
# =============================================================================

def _is_duplicate_and_mark(fingerprint: str) -> bool:
    """
    入力・応答・精錬文などを結合した “会話スニペット” をハッシュ化して既存確認。
    True: 重複あり（登録済み） / False: 新規。
    """
    if not isinstance(fingerprint, str):
        fingerprint = str(fingerprint or "")

    h = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    cache = _load_hash_cache()
    if h in cache:
        return True
    cache[h] = _utc_now_iso_z()
    _save_hash_cache(cache)
    return False


# =============================================================================
# 公開I/F: register_entry
# =============================================================================

def register_entry(payload: Dict[str, Any], resonance_vector: Any) -> Optional[str]:
    """
    CAPS への 1エントリ登録:
      - refined_text 補完
      - 重複（input+refined+response の複合 fingerprint）チェック
      - FAISS 追加
      - メタJSONL 追記（フラット形）
    成功時: vector_id（str）を返す。スキップ時: None。
    """
    try:
        # 必須想定フィールド
        caps_directive = payload.get("caps_directive", {})
        metadata       = payload.get("caps_metadata", {})  # 入力はネスト前提
        scores         = payload.get("evaluation_scores", {})

        # refined_text を確実に持たせる（重複キーに使うため最初に補完）
        refined_text = _ensure_refined_text(metadata)

        if not refined_text.strip():
            print("[index_builder] refined_text が空なので登録スキップ")
            return None

        # 重複チェック（入力と応答も混ぜた“会話スニペット fingerprint”で判定）
        composite_key = "\n".join([
            str(metadata.get("input_text", "")),
            str(refined_text or ""),
            str(metadata.get("response_text", "")),
        ])
        if _is_duplicate_and_mark(composite_key):
            print("[index_builder] 重複（composite fingerprint一致）のため登録スキップ")
            return None

        # vector_id を決定（与えられていなければ新規採番）
        vector_id = metadata.get("vector_id") or str(uuid.uuid4())
        metadata["vector_id"] = vector_id  # 以降の一貫性のため明示

        # ベクトルの整形
        vec = np.array(resonance_vector, dtype="float32")
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        if vec.ndim != 2 or vec.shape[0] != 1:
            raise ValueError(f"[index_builder] resonance_vector の形が不正です: {vec.shape}")

        # FAISS 追加（戻り値は “faiss内での行ID”）
        faiss_id = _append_to_index(vec)

        # フラット形メタを構築して JSONL に追記
        # faiss_idを含めたフラットメタを構築
        flat_meta = _build_flat_meta(vector_id, payload, metadata, scores, faiss_id=faiss_id)

        _write_meta_jsonl(flat_meta)

        print(f"[index_builder] 登録完了 vector_id={vector_id}")
        print(f"[index_builder] wrote meta -> {CAPS_META_PATH}")
        print(f"[index_builder] wrote index -> {CAPS_FAISS_PATH}")
        return vector_id

    except Exception as e:
        print(f"[index_builder] 登録処理でエラー: {e}")
        return None


# =============================================================================
# テスト実行用
# =============================================================================
if __name__ == "__main__":
    # 簡易テスト（必要なら適宜編集）
    dummy_payload = {
        "caps_directive": {
            "action": "store_caps",
            "intent_tag": "test",
            "timestamp": _utc_now_iso_z(),
        },
        "caps_metadata": {
            "refined_text": "Hello world from Mike.",
            "input_text": "Say hello",
            "response_text": "Hello world from Mike.",
            "language": "ja",
            "category": "test",
            "tags": ["test", "hello"]
        },
        "evaluation_scores": {
            "intent_confidence": 0.9
        }
    }
    dummy_vec = np.random.rand(1536).astype("float32")  # 例: 1536次元
    vid = register_entry(dummy_payload, dummy_vec)
    print("vector_id:", vid)