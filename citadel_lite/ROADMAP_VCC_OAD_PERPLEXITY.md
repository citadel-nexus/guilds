# Citadel Lite × VCC × OAD × Perplexity — 統合ロードマップ

> ベース: `BLUEPRINT_INTEGRATION_VCC_OAD_PERPLEXITY_v9.0.md`
> 作成日: 2026-03-01 / 最終更新: 2026-03-06
> ブランチ戦略: `feat/vcc-oad-perplexity-integration` から feature ブランチを切る

---

## 全体アーキテクチャ概要

```
【外部常駐プロセス】
  VCC ──────────────► citadel.vcc.cycle.completed ──►┐
  Perplexity Loop ──► citadel.diagnostic.completed ──►┤
  OAD ──────────────► citadel.oad.*               ──►┤
                                                      ▼
                              NATS JetStream (Stream: VCC_BRIDGE)
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
              loop_orchestrator.py             Citadel Lite Orders UI
              [外部常駐 / go-no-go]                       │
              pause/resume のみ発行                        ▼
                          │                    OrchestratorV3 (src/orchestrator_v3.py)
                          ▼                               │
              Supabase vcc_loop_state       ┌─────────────┼──────────────┐
                                            ▼             ▼              ▼
                                       VCC Adapter   OAD Adapter   Perplexity Adapter
                                       vcc/client    oad/client    perplexity/
                                                     signal_router control_loop_client
                                                                   READ: DD/PH/SB/Notion/GitLab
                                                                   WRITE: Notion/Linear/GitLab/SB
```

---

## Milestone 一覧

| MS    | タイトル                             | ステータス | 依存         |
| ----- | -------------------------------- | ----- | ---------- |
| MS-A1 | Contracts 定義                     | ✅ 完了  | なし         |
| MS-A2 | Adapter Skeletons                | ✅ 完了  | MS-A1      |
| MS-A3 | Diagnostics Loop モジュール           | ✅ 完了  | MS-A2      |
| MS-A4 | OAD Repair Hook                  | ✅ 完了  | MS-A2      |
| MS-A5 | Observability (Datadog)          | ✅ 完了  | MS-A2      |
| MS-A6 | Orchestrator V3 Wire-in          | ✅ 完了  | MS-A3〜A5   |
| MS-A7 | Integrated Demo Run              | ✅ 完了  | MS-A6      |
| MS-B1 | Nemesis L2 Inspector middleware  | ✅ 完了  | MS-A2 (任意) |
| MS-B2 | Nemesis L3 Hunter (Honeypots)    | ✅ 完了  | MS-B1      |
| MS-B3 | Nemesis L4 Oracle + Admin API    | ✅ 完了  | MS-B2      |
| MS-C1 | CGRF CLAUDE.md + 監査スクリプト         | ✅ 完了  | なし         |
| MS-C2 | Notion SMP レジストリ DB              | ✅ 完了  | MS-C1      |
| MS-C3 | VCCSakeReader + CAPS grade 統合    | ✅ 完了  | MS-A1      |
| MS-8  | Stagger Chain (Tiered Inference) | ⏸ 待機  | MS-A2 完了後  |

---

## MS-A1 — Contracts 定義

**目的**: VCC / OAD / Perplexity 間の JSON 契約を dataclass で固める。swap 可能性を最優先。

### 新規ファイル

| ファイル                                                  | 内容                                                                                                                                                                                                    |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/contracts/orders.py`                             | `BuildRequest`, `BuildResult` (`build_checks_passed` フィールド含む)                                                                                                                                         |
| `src/contracts/diagnostics.py`                        | `RepairRequest`, `RepairResult`, `DiagnosticsRequest`, `DiagnosticsReport`, `CitadelHealthSnapshot` (`overall_grade/score`、`health_grade/score`、`vcc_test_*`、`go_no_go` フィールド含む)、`Signal`             |
| `src/integrations/nats/schemas.py`                    | Pydantic schemas: `CycleCompletedPayload` (`vcc_test_passed/failed`)、`DiagnosticCompletedPayload` (`health_grade`, `health_score`)、`TestCompletedPayload`、`BuildControlPayload`、`CitadelNATSEnvelope` |
| `src/integrations/nats/migrations/add_env_column.sql` | `vcc_loop_state` に `env` 列を追加                                                                                                                                                                         |

### 主要 dataclass

```python
# orders.py
@dataclass
class BuildRequest:
    schema: str = "vcc.build_request.v1"
    order_id: str = ""
    repo: str = ""
    target: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BuildResult:
    schema: str = "vcc.build_result.v1"
    order_id: str = ""
    status: str = "ok"          # ok | error | partial
    artifacts: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

# diagnostics.py
@dataclass
class DiagnosticsReport:
    schema: str = "pplx.diagnostics_report.v1"
    order_id: str = ""
    verdict: str = "UNKNOWN"    # OK | DEGRADED | RECOVERING | CRITICAL
    risk: int = 0
    blockers: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)
```

### CGRF v3.0 要件

> 準拠仕様: `blueprints/CGRF-v3.0-Complete-Framework.md`

全新規モジュールに以下の4フィールドを付与する:

```python
_MODULE_NAME    = "module_name"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1                  # Tier 1 (DEVELOPMENT)
_EXECUTION_ROLE = "INTEGRATION"      # INTEGRATION | BACKEND_SERVICE | ...
```

| モジュール                                                                                          | `_EXECUTION_ROLE` |
| ---------------------------------------------------------------------------------------------- | ----------------- |
| `vcc/client.py`, `oad/client.py`, `perplexity/control_loop_client.py`, `nats/bridge_client.py` | `INTEGRATION`     |
| `modules/diagnostics_loop.py`                                                                  | `BACKEND_SERVICE` |
| `monitoring/datadog_adapter.py`                                                                | `INTEGRATION`     |

---

## MS-A2 — Adapter Skeletons

**目的**: VCC / OAD / Perplexity の thin adapter を実装。dry_run=True で実 API 不要で動作。

### 新規ファイル

| ファイル                                                    | 内容                                                                                    |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `src/integrations/vcc/__init__.py`                      | CGRF ヘッダのみ                                                                            |
| `src/integrations/vcc/contracts.py`                     | contracts.py から re-export (互換レイヤー)                                                    |
| `src/integrations/vcc/client.py`                        | `VCCClient` — `build(request) -> BuildResult`                                         |
| `src/integrations/oad/__init__.py`                      | CGRF ヘッダのみ                                                                            |
| `src/integrations/oad/client.py`                        | `OADClient` — `repair(request) -> RepairResult`                                       |
| `src/integrations/oad/signal_router.py`                 | `OADSignalRouter` — `pull_latest_signals() -> List[Signal]`                           |
| `src/integrations/perplexity/__init__.py`               | CGRF ヘッダのみ                                                                            |
| `src/integrations/perplexity/control_loop_client.py`    | `PerplexityControlLoopClient` — `run(request) -> DiagnosticsReport`                   |
| `src/integrations/perplexity/action_executor_client.py` | `PerplexityActionExecutor` — `execute(actions)`                                       |
| `src/integrations/notion_search.py`                     | **[deferred]** スコープ外 — F977 と同様に未実装。既存 `notion_client.py` で代替。MS-9 以降で再評価。       |
| `src/integrations/nats/__init__.py`                     | CGRF ヘッダのみ                                                                            |
| `src/integrations/nats/bridge_client.py`                | `NATSBridgeClient` — `publish()` / `subscribe()` / `wait_for()` (nats.py 使用、未設定時はスタブ) |

### 実装パターン (全 adapter 共通)

```python
class VCCClient:
    def __init__(self, nats_client=None, dry_run: bool = True):
        self._nats = nats_client  # NATSBridgeClient (NATS 経由で VCC を操作)
        self._dry_run = dry_run

    def build(self, request: BuildRequest) -> BuildResult:
        if self._nats is None:
            logger.info("NATSBridgeClient unset — returning stub BuildResult")
            return BuildResult(order_id=request.order_id, status="stub")
        if self._dry_run:
            return BuildResult(order_id=request.order_id, status="dry_run")
        # NATS publish → wait citadel.vcc.cycle.completed
        ...
```

### ENV 変数

> 変数名は `env_param_list.txt` を正とする

| 変数              | 用途                                   |
| --------------- | ------------------------------------ |
| `NATS_URL`      | NATS JetStream 接続先 (VCC Bridge)      |
| `NATS_USER`     | NATS 認証ユーザー (未設定=無認証)                |
| `NATS_PASSWORD` | NATS 認証パスワード (未設定=無認証)               |
| `OAD_PAT`       | OAD 主認証 PAT (`GITLAB_TOKEN` フォールバック) |
| `PPLX_API_KEY`  | Perplexity API キー                    |

---

## MS-A3 — Diagnostics Loop モジュール

**目的**: READ→THINK→WRITE→ASSESS の 4 ステップを `DiagnosticsLoop` クラスに実装。

### 新規ファイル

| ファイル                              | 内容                           |
| --------------------------------- | ---------------------------- |
| `src/modules/diagnostics_loop.py` | `DiagnosticsLoop` — メイン診断ループ |

### DiagnosticsLoop API

```python
class DiagnosticsLoop:
    def run(
        self,
        order_id: str,
        targets: List[str] = None,  # default: all
        dry_run: bool = True,
    ) -> DiagnosticsReport:
        telemetry = self._read(targets)
        diagnosis  = self._think(telemetry)
        self._write(diagnosis)          # Notion + Linear + GitLab
        self._assess(diagnosis)         # Prometheus metrics
        return diagnosis

    def _read(self, targets) -> Dict[str, Any]: ...   # 各ソース集約
    def _think(self, telemetry) -> DiagnosticsReport: ...  # verdict / risk 計算
    def _write(self, report) -> None: ...             # Notion page / Linear issue
    def _assess(self, report) -> None: ...            # metrics emit
```

### READ ソース対応表

| ソース      | クライアント                                   | READ / WRITE |
| -------- | ---------------------------------------- | ------------ |
| Datadog  | `src/monitoring/datadog_adapter.py` (新規) | READ         |
| PostHog  | 既存 or stub                               | READ         |
| Supabase | `src/infra/supabase_mca_mirror.py` (既存)  | READ / WRITE |
| Notion   | `src/infra/notion_mca_client.py` (既存)    | READ / WRITE |
| GitLab   | stub → 後で実装                              | READ / WRITE |
| Stripe   | stub                                     | READ         |
| Metabase | stub                                     | READ         |
| Linear   | stub → 後で実装                              | WRITE        |

---

## MS-A4 — OAD Repair Hook

**目的**: テスト失敗・CI 失敗時に OADClient を呼び出し、RepairResult を audit に記録。

> **設計ベース**: `blueprints/REFLEX-System-Spec-v1.0.md`
> `signal_router.py` が取得する Signal は REFLEX の OBSERVE ステージ入力に相当。
> OAD 内部では OBSERVE→DIAGNOSE→RESPOND→VERIFY→LEARN が走るが、Citadel Lite は OAD Adapter 経由で呼ぶのみ。

### 変更ファイル

- `src/integrations/oad/signal_router.py` — GitLab `pipeline_failed` などを Signal に正規化 (REFLEX OBSERVE 相当)
- `src/modules/diagnostics_loop.py` — `blockers` に OAD シグナルを注入

### シグナル正規化スキーマ

```python
@dataclass
class Signal:
    signal_id: str
    source: str             # "gitlab", "datadog", "posthog" ...
    event_type: str         # "pipeline_failed", "error_spike" ...
    signal_class: str       # "technical" | "business"
    priority: str           # "low" | "medium" | "high" | "critical"
    should_trigger_reflex: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
```

---

## MS-A5 — Observability (Datadog)

**目的**: ループ実行を Datadog に emit。未設定でも no-op で安全。

### 新規ファイル

| ファイル                                | 内容                                                 |
| ----------------------------------- | -------------------------------------------------- |
| `src/monitoring/datadog_adapter.py` | `DatadogAdapter` — `emit_event()`, `emit_metric()` |

### DatadogAdapter API

```python
class DatadogAdapter:
    def emit_event(self, title: str, text: str, tags: List[str] = None) -> bool: ...
    def emit_metric(self, metric: str, value: float, tags: List[str] = None) -> bool: ...
    def read_monitors(self, tag: str = "citadel") -> List[dict]: ...  # READ用
```

### ENV 変数

| 変数           | 用途                      |
| ------------ | ----------------------- |
| `DD_API_KEY` | Datadog API キー          |
| `DD_APP_KEY` | Datadog App キー          |
| `DD_SITE`    | `datadoghq.com` (デフォルト) |

### Prometheus との住み分け

- **Prometheus**: 内部メトリクス (pipeline duration, risk score, agent XP) → 既存 `src/monitoring/metrics.py`
- **Datadog**: 外部観測 (ループ実行結果、ブロッカー通知) → 新規 `datadog_adapter.py`

---

## MS-A6 — Orchestrator V3 Wire-in

**目的**: `OrchestratorV3` の `run_from_event` 内に DiagnosticsLoop + Adapter 呼び出しを最小 touchpoint で追加。

### 変更ファイル

- `src/orchestrator_v3.py` — `__init__` に adapter injection、`_run_from_event_inner` に診断ループ呼び出し

### 変更内容 (差分イメージ)

```python
# __init__ に追加
from src.modules.diagnostics_loop import DiagnosticsLoop  # lazy import

class OrchestratorV3:
    def __init__(self, ..., diagnostics_loop=None):
        ...
        # Diagnostics Loop (Blueprint integration)
        diag_enabled = self.settings.get("diagnostics_loop", {}).get("enabled", False)
        self.diagnostics_loop = diagnostics_loop
        if diag_enabled and diagnostics_loop is None:
            try:
                self.diagnostics_loop = DiagnosticsLoop()
            except Exception as e:
                logger.debug("DiagnosticsLoop not available: %s", e)
```

```python
# _run_from_event_inner の末尾 (mike review の後) に追加
# Diagnostics Loop (Blueprint: READ/THINK/WRITE/ASSESS)
self._run_diagnostics_loop(event, decision)
```

```python
def _run_diagnostics_loop(self, event, decision) -> None:
    if self.diagnostics_loop is None:
        return
    try:
        dry_run = self.settings.get("diagnostics_loop", {}).get("dry_run", True)
        report = self.diagnostics_loop.run(
            order_id=event.event_id,
            dry_run=dry_run,
        )
        self.audit.log("diagnostics_loop", {
            "verdict": report.verdict,
            "risk": report.risk,
            "blockers": report.blockers,
        })
    except Exception as e:
        logger.error("DiagnosticsLoop error (non-fatal): %s", e)
```

### `config/settings.yaml` に追加する設定

```yaml
diagnostics_loop:
  enabled: false   # true にすると本番モードで動作
  dry_run: true
  targets:
    - supabase
    - notion
    - gitlab
```

---

## MS-A7 — Integrated Demo Run

**目的**: `demo/events/ci_failed.sample.json` を単一イベントとして流し、UI → 診断 → 修復 → テスト → アーティファクト の一気通貫を実証。

### Demo フロー

```
1. python -m src.orchestrator_v3 demo/events/ci_failed.sample.json
2. OrchestratorV3
   ├─ DiagnosticsLoop.run()        → out/<id>/diagnostics_report.json
   ├─ VCCAdapter.build()           → out/<id>/build_result.json  (dry_run)
   ├─ OADAdapter.repair()          → out/<id>/repair_result.json (dry_run)
   └─ DatadogAdapter.emit_event()  → no-op (DD_API_KEY 未設定)
3. audit_report.json に diagnostics_loop セクション追加
```

### 確認ポイント

- [ ] `out/<id>/diagnostics_report.json` が生成される
- [ ] `verdict` フィールドに RECOVERING / OK / DEGRADED / CRITICAL のいずれかが入る
- [ ] `blockers` が list[str] で返る
- [ ] dry_run=True のとき外部 API を呼ばない
- [ ] DD_API_KEY 未設定でもエラーにならない

---

## テスト計画

| テストファイル                                     | カバー範囲                                                                                 |
| ------------------------------------------- | ------------------------------------------------------------------------------------- |
| `tests/test_vcc_client.py`                  | `VCCClient` dry_run / stub / token 未設定                                                |
| `tests/test_oad_client.py`                  | `OADClient` repair / signal_router                                                    |
| `tests/test_diagnostics_loop.py`            | `DiagnosticsLoop` 4 ステップ / verdict / blockers + `PerplexityControlLoopClient` dry_run |
| `tests/test_datadog_adapter.py`             | `DatadogAdapter` no-op / emit dry_run                                                 |
| `tests/test_orchestrator_v3_diagnostics.py` | OrchestratorV3 に diagnostics_loop 注入して e2e                                            |
| `tests/test_nats_bridge.py`                 | `NATSBridgeClient` publish/subscribe/wait_for スタブ動作                                   |
| `tests/test_nemesis_inspector.py`           | `NemesisInspectorMiddleware` — SQLi/XSS/SSRF ブロック・NEMESIS_ENABLED=false 時のスキップ        |
| `tests/test_nemesis_honeypots.py`           | `honeypot_router` — 囮エンドポイント応答・Supabase 記録・NATS 発行                                    |
| `tests/test_nemesis_oracle.py`              | `NemesisOracle` 分類・`GeoAggregator` no-op・`nemesis_api` ヘルスチェック                        |
| `tests/test_stagger_chain.py`               | Stagger Chain ティア昇格フロー・F980〜F984 Reflex パターン (MS-8 待機中)                               |

---

## ファイル追加サマリー

```
src/
├── contracts/
│   ├── orders.py           ← NEW (MS-A1)
│   └── diagnostics.py      ← NEW (MS-A1)
├── integrations/
│   ├── vcc/
│   │   ├── __init__.py     ← NEW (MS-A2)
│   │   ├── contracts.py    ← NEW (MS-A2)
│   │   └── client.py       ← NEW (MS-A2)
│   ├── oad/
│   │   ├── __init__.py     ← NEW (MS-A2)
│   │   ├── client.py       ← NEW (MS-A2)
│   │   └── signal_router.py ← NEW (MS-A2, MS-A4)
│   ├── perplexity/
│   │   ├── __init__.py     ← NEW (MS-A2)
│   │   ├── control_loop_client.py    ← NEW (MS-A2, MS-A3)
│   │   └── action_executor_client.py ← NEW (MS-A2, MS-A3)
│   ├── notion_search.py    ← NEW (MS-A2, optional)
│   └── nats/
│       ├── __init__.py         ← NEW (MS-A1/A2)
│       ├── bridge_client.py    ← NEW (MS-A2)
│       ├── schemas.py          ← NEW (MS-A1)
│       └── migrations/
│           └── add_env_column.sql ← NEW (MS-A1)
├── modules/
│   └── diagnostics_loop.py ← NEW (MS-A3)
├── monitoring/
│   └── datadog_adapter.py  ← NEW (MS-A5)
└── orchestrator_v3.py      ← MODIFY (MS-A6)

config/
└── settings.yaml           ← MODIFY (MS-A6, diagnostics_loop セクション追加)

tests/
├── test_vcc_client.py                        ← NEW
├── test_oad_client.py                        ← NEW
├── test_diagnostics_loop.py                  ← NEW
├── test_datadog_adapter.py                   ← NEW
└── test_orchestrator_v3_diagnostics.py       ← NEW
```

---

---

## MS-B1 — Nemesis L2 Inspector middleware

**目的**: FastAPI に AI ファイアウォール middleware をマウント。`NEMESIS_ENABLED=false` のデフォルトで既存テストに影響ゼロ。

### 新規ファイル

| ファイル                              | 内容                                                                 |
| --------------------------------- | ------------------------------------------------------------------ |
| `middleware/nemesis_inspector.py` | `NemesisInspectorMiddleware` — SQLi / XSS / SSRF / プロンプトインジェクション検出 |
| `middleware/cors_hardening.py`    | CORS ハードニング (`CORSMiddleware` 強化版)                                 |

### main.py 変更内容

```python
# src/api/main.py に追記
import os
if os.getenv("NEMESIS_ENABLED") == "true":
    from middleware.nemesis_inspector import NemesisInspectorMiddleware
    app.add_middleware(NemesisInspectorMiddleware)
    from middleware.cors_hardening import add_cors
    add_cors(app)
```

### CGRF v3.0 要件

```python
_MODULE_NAME    = "nemesis_inspector"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
```

### ENV 変数

| 変数                         | 用途                        |
| -------------------------- | ------------------------- |
| `NEMESIS_ENABLED`          | `true` で middleware をマウント |
| `NEMESIS_THREAT_THRESHOLD` | 遮断閾値 (デフォルト: 0.7)         |
| `ABUSEIPDB_KEY`            | AbuseIPDB IP レピュテーションチェック |

---

## MS-B2 — Nemesis L3 Hunter (Honeypots)

**目的**: 囮エンドポイントで探索行為を検出・記録・ブラックリスト化。

### 新規ファイル

| ファイル                          | 内容                                                                |
| ----------------------------- | ----------------------------------------------------------------- |
| `routes/nemesis_honeypots.py` | `honeypot_router` — `/admin`, `/.env`, `/wp-login.php` 等の囮エンドポイント |

### main.py 変更内容

```python
if os.getenv("NEMESIS_ENABLED") == "true":
    from routes.nemesis_honeypots import honeypot_router
    app.include_router(honeypot_router)
```

### Supabase

- `migrations/20260226_nemesis.sql`: `nemesis_honeypot_hits` テーブル作成

### NATS 発行

- `citadel.nemesis.l3.honeypot_hit` (Stream: `CITADEL_NEMESIS`)

---

## MS-B3 — Nemesis L4 Oracle + Admin API

**目的**: ML 分類器 + GeoIP 集約 + Nemesis 管理 API + NATS ストリーム確立。

### 新規ファイル

| ファイル                                 | 内容                                                                              |
| ------------------------------------ | ------------------------------------------------------------------------------- |
| `services/nemesis_oracle.py`         | `NemesisOracle` — ML 分類器 (リクエスト→脅威スコア)                                          |
| `services/nemesis_retrain.py`        | `NemesisRetrain` — オンライン再学習                                                     |
| `services/nemesis_geo_aggregator.py` | `GeoAggregator` — MaxMind GeoIP 集約                                              |
| `routes/nemesis_api.py`              | `/api/nemesis/health`, `/api/nemesis/dashboard/summary`, `/api/nemesis/threats` |
| `config/nats-nemesis.yaml`           | `CITADEL_NEMESIS` + `CITADEL_NEMESIS_ALERTS` stream 定義                          |
| `migrations/20260226_nemesis.sql`    | `nemesis_events`, `nemesis_threats` テーブル                                        |

### ENV 変数

| 変数                       | 用途                     |
| ------------------------ | ---------------------- |
| `NEMESIS_ADMIN_TOKEN`    | `/api/nemesis/*` 認証    |
| `NEMESIS_QUARANTINE_TTL` | 隔離 TTL (秒、デフォルト: 3600) |
| `GEOIP_ACCOUNT_ID`       | MaxMind アカウント ID       |
| `GEOIP_LICENSE_KEY`      | MaxMind ライセンスキー        |

### Datadog メトリクス

| メトリクス                          | 型         | 説明                 |
| ------------------------------ | --------- | ------------------ |
| `nemesis.l2.inspector.blocks`  | Counter   | L2 遮断数             |
| `nemesis.l3.honeypot.hits`     | Counter   | L3 ハニーポット命中数       |
| `nemesis.l4.oracle.risk_score` | Histogram | L4 Oracle リスクスコア分布 |
| `nemesis.l4.oracle.latency_ms` | Histogram | L4 推論レイテンシ         |

> MS-B4+ (L5 Shield / L6 Compliance / Red Team): インフラ整備 (Ansible / Helm / Terraform) が完了後に着手。

---

## リスクと軽減策

| リスク                     | 軽減策                                                                             |
| ----------------------- | ------------------------------------------------------------------------------- |
| VCC の実装が不明              | contract-first adapter として実装し、実装が判明したら binding を差し替える                           |
| 外部 API (401/429)        | `dry_run=True` をデフォルト、preflight チェック + blockers list に明示                        |
| 診断データが無音で劣化             | `verdict` + `blockers` の明示的なリターンで劣化を可視化                                         |
| スコープクリープ                | Adapter interface + 最小 wiring のみ。Nemesis L5+/RT は MS-B4+ として分離し、MS-B1〜B3 を個別に着手 |
| OrchestratorV3 の既存テスト破壊 | `diagnostics_loop=None` をデフォルトにし、enabled=false で完全スキップ                          |

---

## MS-8 — Stagger Chain (Tiered Inference Pipeline)

**目的**: `stagger_chain.py` による Haiku→Sonnet→Sonnet→Opus のティアード推論パイプラインを実装し、Citadel Lite 内部の品質自己修正ループを確立する。

> **⏸ 待機中**: `CONFIDENCE_WRAPPER` JSON 形式の衝突問題解決後に着手。`perplexity_control_loop_v2.py` の `vault_loader` ハード依存の分離も前提条件。

### 前提条件

- [ ] MS-A2 完了 (`NATSBridgeClient` 接続設定確立)
- [ ] `CONFIDENCE_WRAPPER` 出力 JSON と professor output format の衝突を解消
- [ ] `perplexity_control_loop_v2.py` の `vault_loader` 依存を optional に変更

### 推論ティア構成 (triage → workhorse → premium → heavy)

| ティア         | モデル        | 役割                                  |
| ----------- | ---------- | ----------------------------------- |
| `triage`    | **Haiku**  | 初期トリアージ・高速判定・ルーティング                 |
| `workhorse` | **Sonnet** | 主力処理・標準品質                           |
| `premium`   | **Sonnet** | 高品質処理・精密分析 (temperature / top_p 強化) |
| `heavy`     | **Opus**   | 最高品質・複雑問題解決・最終エスカレーション              |

**品質ゲート**: `batch_audit.py` — 各ティア出力のスコアを審査し、閾値未達時に上位ティアへ自動エスカレーション。

### Reflex パターン (F980〜F984)

> OAD の F924/F950/F960 は外部 OAD システムが管理する。F980〜F984 は Citadel Lite 内 `stagger_chain.py` が独立して管理する自己修正ループ。

| パターンコード | 内容                                         | エスカレーション先                  | トリガー条件                  |
| ------- | ------------------------------------------ | -------------------------- | ----------------------- |
| F980    | Implementation drift (実装ドリフト)              | `workhorse` → `premium` 昇格 | 仕様と実装の差分スコア > 閾値        |
| F981    | Quality regression (品質劣化)                  | 前ティア出力を再評価・再生成             | batch_audit スコア低下トレンド検出 |
| F982    | Pipeline halt (パイプライン停止)                   | フォールバック応答を即時返却             | タイムアウト / 接続エラー連続        |
| F983    | Evolution stall (進化停止)                     | `heavy` (Opus) で強制解決       | 3 回連続で品質閾値未達            |
| F984    | College convergence failure (College 収束失敗) | AIS College へエスカレーション      | professor 合意スコア < 最低水準  |

### 新規ファイル

| ファイル                          | 内容                                                      | CGRF EXECUTION_ROLE |
| ----------------------------- | ------------------------------------------------------- | ------------------- |
| `src/stagger_chain.py`        | `StaggerChain` — ティアード推論エントリポイント・F980〜F984 Reflex ループ管理 | `AGENT`             |
| `src/batch_audit.py`          | `BatchAudit` — 各ティア出力の品質ゲート・スコア計算・エスカレーション判定            | `BACKEND_SERVICE`   |
| `tests/test_stagger_chain.py` | Stagger Chain + F980〜F984 全パターン単体テスト                    | —                   |

### CGRF v3.0 ヘッダー

```python
# src/stagger_chain.py
_MODULE_NAME    = "stagger_chain"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "AGENT"

# src/batch_audit.py
_MODULE_NAME    = "batch_audit"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "BACKEND_SERVICE"
```

### テスト計画 (MS-8)

| テストファイル                         | カバー範囲                                                                      |
| ------------------------------- | -------------------------------------------------------------------------- |
| `tests/test_stagger_chain.py`   | triage→workhorse→premium→heavy 昇格フロー / dry_run モード / F980〜F984 各パターントリガー検証 |
| `tests/test_cgrf_audit.py`      | CGRF 4フィールド検出 / strict モード / レポート生成 (MS-C1)                                |
| `tests/test_smp_notion_sync.py` | SMP レジストリ同期 / dry_run / Notion API モック (MS-C2)                             |
| `tests/test_sake_reader.py`     | `.sake` ファイル読み込み / CAPS grade マッピング / 不正ファイル拒否 (MS-C3)                     |

---

## MS-C1 — CGRF コンプライアンス CLAUDE.md + 監査スクリプト

**目的**: 全開発者が CGRF 4フィールド要件・SRS コード体系を参照できる基盤を整備し、CI で自動監査する。

### 新規ファイル

| ファイル                       | 内容                                                    |
| -------------------------- | ----------------------------------------------------- |
| `CLAUDE.md` (リポジトリルート)     | SRS コード一覧・TaskIR 13ブロック規約・CGRF 4フィールド要件・開発規約          |
| `tools/cgrf_audit.py`      | 全 `.py` モジュールの CGRF 4フィールド存在確認 → JSON/Markdown レポート生成 |
| `tests/test_cgrf_audit.py` | cgrf_audit.py の単体テスト                                  |

### 変更ファイル

| ファイル                       | 変更内容                                             |
| -------------------------- | ------------------------------------------------ |
| `.gitlab-ci.yml`           | `cgrf-compliance-check` ジョブ追加                    |
| `.github/workflows/ci.yml` | `cgrf-compliance-check` step 追加 (GitHub Actions) |

### CGRF ヘッダー

```python
# tools/cgrf_audit.py
_MODULE_NAME    = "cgrf_audit"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 0
_EXECUTION_ROLE = "TOOL"
```

### ENV 変数

| 変数                  | 用途                               | デフォルト   |
| ------------------- | -------------------------------- | ------- |
| `CGRF_AUDIT_STRICT` | `true` で違反時に exit code 1 (CI 失敗) | `false` |

### 確認ポイント

- [ ] `tools/cgrf_audit.py --report` で JSON レポートが生成される
- [ ] 4フィールドが欠けたモジュールが violations に列挙される
- [ ] `--strict` フラグで violations > 0 なら exit 1
- [ ] CI ジョブが pass (strict=false) / fail (strict=true + violations) で動作する

---

## MS-C2 — Notion SMP レジストリ DB

**目的**: citadel_lite 全モジュールの SMP メタデータ (module_name, version, CGRF tier, CAPS grade, SRS codes) を Notion DB に同期し、MCA / EVO Tracker と一元管理する。

### 新規ファイル

| ファイル                            | 内容                                                                            |
| ------------------------------- | ----------------------------------------------------------------------------- |
| `src/infra/smp_notion_sync.py`  | `sync_smp_registry(modules, dry_run=True)` — モジュールリストを Notion SMP DB に upsert |
| `tests/test_smp_notion_sync.py` | dry_run / Notion API モック / DB upsert 検証                                       |

### 変更ファイル

| ファイル                             | 変更内容                                                   |
| -------------------------------- | ------------------------------------------------------ |
| `src/infra/notion_mca_client.py` | `create_smp_entry()` / `update_smp_entry()` ブロックビルダー追加 |

### CGRF ヘッダー

```python
# src/infra/smp_notion_sync.py
_MODULE_NAME    = "smp_notion_sync"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
```

### ENV 変数

| 変数                          | 用途              | デフォルト |
| --------------------------- | --------------- | ----- |
| `NOTION_TOKEN`              | Notion API (既存) | (既存)  |
| `NOTION_SMP_REGISTRY_DB_ID` | SMP レジストリ DB ID | —     |

### Notion SMP レジストリ DB スキーマ

| プロパティ             | 型            | 内容                                                      |
| ----------------- | ------------ | ------------------------------------------------------- |
| `module_name`     | Title        | モジュール識別子                                                |
| `version`         | Text         | `_MODULE_VERSION`                                       |
| `cgrf_tier`       | Select       | `T0`〜`T3`                                               |
| `execution_role`  | Select       | `INTEGRATION` \| `AGENT` \| `BACKEND_SERVICE` \| `TOOL` |
| `caps_grade`      | Select       | `T1`〜`T5` \| `UNKNOWN`                                  |
| `srs_codes`       | Multi-select | 紐づく SRS コード                                             |
| `last_synced`     | Date         | 最終同期日時                                                  |
| `compliance_pass` | Checkbox     | CGRF 4フィールド完全準拠フラグ                                      |

### 確認ポイント

- [ ] `dry_run=True` で Notion API を呼ばずに同期ペイロードが返る
- [ ] `NOTION_SMP_REGISTRY_DB_ID` 未設定で no-op (エラーなし)
- [ ] 存在しないエントリは create、既存エントリは update

---

## MS-C3 — VCCSakeReader + CAPS grade 統合

**目的**: `.sake` プロファイルを Citadel Lite が消費できる thin Adapter を追加し、CAPS trust_score を `CitadelHealthSnapshot.code.caps_grade` に反映する。

### 新規ファイル

| ファイル                                  | 内容                                                    | `_EXECUTION_ROLE` |
| ------------------------------------- | ----------------------------------------------------- | ----------------- |
| `src/integrations/vcc/sake_reader.py` | `VCCSakeReader` — `.sake` ファイル読み込み + CAPS grade マッピング | `INTEGRATION`     |
| `tests/test_sake_reader.py`           | `load()` / `to_health_grade()` / 不正ファイル拒否テスト          | —                 |

### 変更ファイル

| ファイル                           | 変更内容                                                    |
| ------------------------------ | ------------------------------------------------------- |
| `src/contracts/diagnostics.py` | `HealthCodeMetrics.caps_grade: str = "UNKNOWN"` フィールド追加 |

### CAPS grade マッピング

| `trust_score` 範囲 | grade | 意味   |
| ---------------- | ----- | ---- |
| `>= 0.90`        | `T1`  | 最高信頼 |
| `>= 0.75`        | `T2`  | 高信頼  |
| `>= 0.60`        | `T3`  | 標準   |
| `>= 0.40`        | `T4`  | 要注意  |
| `< 0.40`         | `T5`  | 低信頼  |

### CGRF ヘッダー

```python
# src/integrations/vcc/sake_reader.py
_MODULE_NAME    = "sake_reader"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
```

### ENV 変数

| 変数                     | 用途                     | デフォルト            |
| ---------------------- | ---------------------- | ---------------- |
| `VCC_SAKE_PROFILE_DIR` | `.sake` プロファイル配置ディレクトリ | `sake_profiles/` |

### 確認ポイント

- [ ] `VCCSakeReader.load("path.sake")` で SakeFile dataclass が返る
- [ ] `to_health_grade({"trust_score": 0.8})` → `"T2"`
- [ ] 不正 JSON / 存在しないファイルで `ValueError` が送出される
- [ ] `CitadelHealthSnapshot.code.caps_grade` に grade がセットされる

---

## Out-of-Scope

- **Nemesis L5 Shield / L6 Compliance / Red Team (MS-B4+)**: インフラ整備 (Ansible / Helm / Terraform) 完了後に判断
- **MS-8 (Stagger Chain)**: `CONFIDENCE_WRAPPER` JSON 衝突問題解決後に着手 — 現時点は設計のみ
- PostHog / Stripe / Metabase の実 API 実装: stub のみ
- **F941 SAKEBuilder 本体**: `CITADEL_LLM/SAKE/` 固有依存 — citadel_lite_repo に組み込まない
- **F977 Lineage Tracker**: AIMB ヘッダー生成フロー全体が `CITADEL_LLM/SAKE/` 専用
- **F991 Schema Generator**: TaskIR JSON → Pydantic 自動生成は `CITADEL_LLM` 専用ツール
- **F999 テストハーネス**: `.sake` ファイル消費テストは `CITADEL_LLM/SAKE/` パス依存

---

*このロードマップは `BLUEPRINT_INTEGRATION_VCC_OAD_PERPLEXITY_v9.0.md` を実装プランに変換したものです。*
*実装開始前にこのドキュメントをレビューし、優先 MS を確認してください。*
