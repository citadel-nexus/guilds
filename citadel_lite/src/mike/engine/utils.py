import hashlib
import json
from pathlib import Path

def hash_text(text: str) -> str:
    """
    入力文字列に対してSHA256ハッシュを計算し、先頭16文字を返す。
    """
    hash_obj = hashlib.sha256(text.strip().encode("utf-8"))
    return hash_obj.hexdigest()[:16]

def load_previous_hashes(path: str) -> dict:
    """
    指定されたJSONファイルからハッシュ辞書を読み込む。

    Args:
        path (str): キャッシュファイルのパス

    Returns:
        dict: {vector_id: hash} 形式の辞書
    """
    file = Path(path)
    if file.exists():
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"⚠️ ハッシュキャッシュの読み込みに失敗しました（破損の可能性）: {path}")
    return {}

def save_hashes(hashes: dict, path: str):
    """
    ハッシュ辞書を指定されたJSONファイルに保存する。

    Args:
        hashes (dict): {vector_id: hash} 形式の辞書
        path (str): 保存先パス
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(hashes, indent=2, ensure_ascii=False), encoding="utf-8")