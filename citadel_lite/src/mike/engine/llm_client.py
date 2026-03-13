# engine/llm_client.py
import os, itertools, random, json
from typing import Any, Dict, Optional, Tuple, List
from dotenv import load_dotenv
from types import SimpleNamespace

# OpenAI SDK は「使う場合だけ」import（環境によって未インストール/差し替えもあり得るため）
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

try:
    import httpx  # type: ignore
except Exception:
    httpx = None  # type: ignore

load_dotenv(override=True)

# 優先: LM Studio / 互換API（またはOpenAI互換エンドポイント）
PRIMARY_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
PRIMARY_MODEL    = os.getenv("OPENAI_MODEL", "openai/gpt-oss-20b")
print(f"[llm_client] PRIMARY_BASE_URL={PRIMARY_BASE_URL} PRIMARY_MODEL={PRIMARY_MODEL}")

# フォールバック: OpenAI 公式
FALLBACK_BASE_URL = "https://api.openai.com/v1"
FALLBACK_MODEL    = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")

#
# Embeddings は別系統に逃がせるようにする（Ollama gpt-oss:20b は embeddings 非対応）
# 既存コードが `client.embeddings.create(...)` を叩く前提でも壊れないよう、
# get_llm_client() が返す client に embeddings proxy を付与する。
#
EMBEDDING_PROVIDER = (os.getenv("MIKE_EMBEDDING_PROVIDER", "openai") or "").strip().lower()
EMBEDDING_BASE_URL = os.getenv("OPENAI_EMBEDDING_BASE_URL", FALLBACK_BASE_URL)
EMBEDDING_MODEL    = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_TIMEOUT  = float(os.getenv("OPENAI_EMBEDDING_TIMEOUT", "60.0"))


def _normalize_base_url(url: str) -> str:
    """
    - 前後の空白/引用符を除去
    - 末尾スラッシュ除去
    - /v1 が無ければ付与（OpenAI互換を想定）
    """
    u = (url or "").strip().strip('"').strip("'").rstrip("/")
    if not u:
        return u
    # すでに /v1/... の形ならそのまま、/v1 が無ければ付与
    if "/v1" not in u.split("?")[0]:
        u = u + "/v1"
    return u

PRIMARY_BASE_URL = _normalize_base_url(PRIMARY_BASE_URL)

MIKE_LLM_PROVIDER = (os.getenv("MIKE_LLM_PROVIDER", "openai_compat") or "").strip().lower()

def _collect_keys(prefix: str) -> list[str]:
    """
    環境変数からキー群を収集:
      - <PREFIX>
      - <PREFIX>_1 .. <PREFIX>_9
    空文字/未定義/重複は除外。
    """
    keys = []
    cand = [os.getenv(prefix, ""), *[os.getenv(f"{prefix}_{i}", "") for i in range(1, 10)]]
    for k in cand:
        k = (k or "").strip()
        if not k:
            continue
        if k not in keys:
            keys.append(k)
    return keys

class _CompletionsProxy:
    def __init__(self, pool: "PooledClient"):
        self._pool = pool
    def create(self, **kwargs):
        client = self._pool.next_client()
        return client.chat.completions.create(**kwargs)

class _ChatProxy:
    def __init__(self, pool: "PooledClient"):
        self.completions = _CompletionsProxy(pool)

class _ModelsProxy:
    def __init__(self, pool: "PooledClient"):
        self._pool = pool
    def list(self):
        # 健康チェックは最初のクライアントで
        client = self._pool.peek_client()
        return client.models.list()

class _EmbeddingsProxy:
    def __init__(self, pool: "PooledClient", model: str):
        self._pool = pool
        self._model = model
    def create(self, **kwargs):
        """
        OpenAI SDK 互換: client.embeddings.create(model=..., input=...)
        呼び出し側が model を指定していない場合は EMBEDDING_MODEL を強制する。
        """
        client = self._pool.next_client()
        if "model" not in kwargs or not kwargs.get("model"):
            kwargs["model"] = self._model
        return client.embeddings.create(**kwargs)


class HTTPXOpenAICompat:
    """
    OpenAI互換エンドポイント（例: Ollama / LM Studio）を /v1 で叩く軽量クライアント。
    - models.list() -> GET /v1/models
    - chat.completions.create() -> POST /v1/chat/completions
    """
    def __init__(self, api_key: str, base_url: str, timeout: float = 60.0):
        if httpx is None:
            raise RuntimeError("httpx が見つかりません。`pip install httpx` してください。")
        self._api_key = (api_key or "").strip()
        self._base_url = _normalize_base_url(base_url)
        self._timeout = timeout

        self.chat = type("Chat", (), {})()
        self.chat.completions = type("Completions", (), {})()
        self.chat.completions.create = self._chat_completions_create

        self.models = type("Models", (), {})()
        self.models.list = self._models_list

        # OpenAI SDK 互換: embeddings が呼ばれた場合に分かりやすく落とす
        # (Ollama gpt-oss は embeddings 非対応のため)
        self.embeddings = type("Embeddings", (), {})()
        self.embeddings.create = self._embeddings_create

    def _headers(self) -> Dict[str, str]:
        # Ollama の OpenAI互換は認証必須ではない場合もあるが、互換性のため Bearer は付与
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    @staticmethod
    def _ns(obj: Any) -> Any:
        """
        dict/list を OpenAI SDK っぽく attribute アクセス可能なオブジェクトへ変換する。
        例: resp["choices"][0]["message"]["content"] -> resp.choices[0].message.content
        """
        if isinstance(obj, dict):
            return SimpleNamespace(**{k: HTTPXOpenAICompat._ns(v) for k, v in obj.items()})
        if isinstance(obj, list):
            return [HTTPXOpenAICompat._ns(v) for v in obj]
        return obj

    def _models_list(self) -> Dict[str, Any]:
        url = f"{self._base_url}/models"
        with httpx.Client(timeout=self._timeout) as c:
            r = c.get(url, headers=self._headers())
            r.raise_for_status()
            # OpenAI SDK 互換の形に寄せて返す（最低限 data を持たせる）
            data = r.json()
            # /v1/models の OpenAI 形式を想定。互換が違っても壊れにくいようにそのまま保持。
            return data

    def _chat_completions_create(self, **kwargs) -> Dict[str, Any]:
        url = f"{self._base_url}/chat/completions"
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(url, headers={"Content-Type": "application/json", **self._headers()}, json=kwargs)
            try:
                r.raise_for_status()
            except Exception as e:
                # Ollama 側の 500/400 の本文を見たいので、可能なら body を付けて投げる
                body = ""
                try:
                    body = r.text
                except Exception:
                    pass
                raise RuntimeError(f"OpenAI-compat chat.completions failed: {e} body={body[:2000]}") from e
            # ここが重要: dict のままだと呼び出し側が .choices にアクセスできず落ちる
            raw = r.json()
            resp = self._ns(raw)
            # デバッグ/互換性のため raw も残す
            try:
                setattr(resp, "_raw", raw)
            except Exception:
                pass
            return resp

    def _embeddings_create(self, **kwargs) -> Any:
        """
        OpenAI SDK 互換の呼び出しが来た場合の明示的エラー。
        （CLI_Mike 側が embedding を要求しているなら、embedding は OpenAI 側へ分離するのが安全）
        """
        raise RuntimeError(
            "This OpenAI-compat endpoint/model does not support embeddings. "
            "Use OpenAI (e.g., text-embedding-3-small) for embeddings, or switch embedding provider."
        )

class PooledClient:
    """
    互換クライアントの軽量プール。
    .chat.completions.create(...) を呼ぶたびに次のキーを選択。
    """
    def __init__(self, clients: list[Any]):
        if not clients:
            raise RuntimeError("クライアントが0件です。")
        self._clients = clients
        self._cycle   = itertools.cycle(range(len(self._clients)))
        for _ in range(random.randint(0, len(self._clients)-1)):
            next(self._cycle)
        self.chat   = _ChatProxy(self)
        self.models = _ModelsProxy(self)

    def next_client(self) -> Any:
        idx = next(self._cycle)
        return self._clients[idx]

    def peek_client(self) -> Any:
        return self._clients[0]

def _build_primary_pool(keys: list[str], base_url: str) -> PooledClient:
    """
    provider に応じて Primary クライアントプールを生成。
    """
    use_sdk = MIKE_LLM_PROVIDER in ("openai", "openai_sdk", "sdk")
    if use_sdk:
        if OpenAI is None:
            raise RuntimeError("OpenAI SDK が import できません。`pip install openai` を確認してください。")
        return PooledClient([OpenAI(api_key=k, base_url=base_url) for k in keys])
    # openai互換（Route A）
    return PooledClient([HTTPXOpenAICompat(api_key=k, base_url=base_url) for k in keys])

def _build_embedding_pool() -> Optional[Tuple[PooledClient, str]]:
    """
    embeddings 用のプールを作る。
    - 既定: OpenAI SDK を使って OpenAI 公式（または指定の BASE_URL）へ
    - もし env で embeddings を無効化したい場合: MIKE_EMBEDDING_PROVIDER=none
    """
    if EMBEDDING_PROVIDER in ("none", "off", "disable", "disabled"):
        return None

    # embeddings は基本 OpenAI SDK 前提（互換HTTPで embeddings を叩くニーズがあるなら後で拡張）
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK が import できません。embeddings を使うなら `pip install openai` を確認してください。")

    # まず専用キー（OPENAI_EMBEDDING_API_KEY[_n]）を優先
    emb_keys = _collect_keys("OPENAI_EMBEDDING_API_KEY")
    if not emb_keys:
        # 次に fallback キー群（OPENAI_FALLBACK_KEY[_n]）
        emb_keys = _collect_keys("OPENAI_FALLBACK_KEY")
    if not emb_keys:
        # それも無ければ通常の OPENAI_API_KEY 群（OpenAI運用時に備えて）
        emb_keys = _collect_keys("OPENAI_API_KEY")

    if not emb_keys:
        raise RuntimeError("embeddings 用のAPIキーが見つかりません。OPENAI_EMBEDDING_API_KEY もしくは OPENAI_FALLBACK_KEY を設定してください。")

    base = _normalize_base_url(EMBEDDING_BASE_URL)
    pool = PooledClient([OpenAI(api_key=k, base_url=base) for k in emb_keys])
    # models.list() で疎通確認（OpenAI公式/互換の想定）
    pool.models.list()
    return pool, EMBEDDING_MODEL


def get_llm_client():
    """
    優先: PRIMARY_BASE_URL に対して OPENAI_API_KEY / OPENAI_API_KEY_1.. をプール運用。
    失敗時は OPENAI_FALLBACK_KEY 群で OpenAI 公式へフォールバック。
    """
    primary_keys  = _collect_keys("OPENAI_API_KEY")
    fallback_keys = _collect_keys("OPENAI_FALLBACK_KEY")

    # まずはプライマリへ
    try:
        # 互換API向けはダミーキーでも動くことが多いので、未設定なら "ollama" を採用
        # OpenAI SDK を使う運用の場合はキー必須なので、未設定で落ちる
        if not primary_keys:
            if MIKE_LLM_PROVIDER in ("openai", "openai_sdk", "sdk"):
                raise RuntimeError("OPENAI_API_KEY が未設定です（OpenAI SDK 運用）。")
            primary_keys = ["ollama"]

        client = _build_primary_pool(primary_keys, base_url=PRIMARY_BASE_URL)
        # 健康チェックは import 時に実行しない (起動時ネットワーク障害で落ちるため)
        # 疎通確認が必要な場合は verify_llm_connection() を明示的に呼ぶこと

        # embeddings を別プールで付与（既存コードが client.embeddings.create を呼べるように）
        try:
            emb = _build_embedding_pool()
            if emb is not None:
                emb_pool, emb_model = emb
                client.embeddings = _EmbeddingsProxy(emb_pool, emb_model)  # type: ignore[attr-defined]
                print(f"[llm_client] EMBEDDINGS via {EMBEDDING_BASE_URL} model={emb_model}")
        except Exception as ee:
            # 既存挙動を壊さないため、embeddings 付与に失敗しても primary 自体は返す
            print(f"[WARN] Embedding client attach failed (continuing without embeddings): {ee}")

        return client, PRIMARY_MODEL
    except Exception as e:
        print(f"[WARN] Primary接続に失敗。Fallbackへ: {e}")
        if not fallback_keys:
            raise
        # Fallback は OpenAI 公式なので SDK を想定（互換HTTPで叩いてもよいが、ここは既存互換維持）
        if OpenAI is None:
            raise RuntimeError("OpenAI SDK が import できないため、Fallback(OpenAI公式)に行けません。")
        fb = PooledClient([OpenAI(api_key=k, base_url=FALLBACK_BASE_URL) for k in fallback_keys])
        # 健康チェック
        fb.models.list()


        # Fallback 側にも embeddings 付与（必要なら）
        try:
            emb = _build_embedding_pool()
            if emb is not None:
                emb_pool, emb_model = emb
                fb.embeddings = _EmbeddingsProxy(emb_pool, emb_model)  # type: ignore[attr-defined]
                print(f"[llm_client] EMBEDDINGS via {EMBEDDING_BASE_URL} model={emb_model}")
        except Exception as ee:
            print(f"[WARN] Embedding client attach failed (fallback continuing without embeddings): {ee}")


        return fb, FALLBACK_MODEL
