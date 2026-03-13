# CLAUDE.md — Citadel Lite Repository Conventions
# ================================================
# CGRF v3.0 Compliance Reference · SRS Code Registry · TaskIR 13-Block Spec
# Version: 1.0.0 | Updated: 2026-03-06

---

## 1. Project Overview

**Citadel Lite** は VCC (Virtual Construction Crew) · OAD (Oracle Augmented Diagnostics) ·
Perplexity Control Loop を統合する自律オーダー処理システム。

| リポジトリ | 役割 |
| --------- | ---- |
| `citadel_lite_repo` | 正 (God Repo) — 実装の唯一の正典 |
| `CNWB/citadel_lite` | 開発統合先 — citadel_lite_repo から定期マージ |

---

## 2. CGRF v3.0 — 4フィールド必須要件

全 Python モジュール (`src/**/*.py`) に以下の4フィールドを付与すること。

```python
_MODULE_NAME    = "module_name"        # ファイル名（拡張子なし）と一致させる
_MODULE_VERSION = "1.0.0"             # semver
_CGRF_TIER      = 1                   # 0=Experimental / 1=Dev / 2=Prod / 3=Mission-Critical
_EXECUTION_ROLE = "INTEGRATION"       # 下表参照
```

### `_EXECUTION_ROLE` 有効値

| 値 | 用途 |
| -- | ---- |
| `AGENT` | 自律エージェント (fixer, sherlock, sentinel …) |
| `INTEGRATION` | 外部 API adapter / bridge / client |
| `BACKEND_SERVICE` | 内部バックグラウンドサービス (diagnostics_loop …) |
| `TOOL` | 開発ツール / audit スクリプト |
| `CONTRACT` | データ型定義 / dataclass 集約 |
| `TEST_SUPPORT` | conftest / テスト用フィクスチャ |

### Tier 定義

| Tier | 名称 | test coverage | docstring | CGRF metadata |
| ---- | ---- | ------------- | --------- | ------------- |
| 0 | Experimental | — | 任意 | 任意 |
| 1 | Development | ≥ 50% | 必須 | 必須 |
| 2 | Production | ≥ 80% | 必須 | 必須 |
| 3 | Mission-Critical | ≥ 95% | 必須 | 必須 |

### フィールド配置ルール

```python
"""Module docstring (required for Tier 1+)."""
from __future__ import annotations
# ... imports ...

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "module_name"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────
```

---

## 3. SRS コード体系

### Citadel Lite 内部 SRS コード

| コード | 名称 | 説明 |
| ------ | ---- | ---- |
| `SRS-FIXER-*` | Fixer Agent | CI 失敗・コードエラー自動修正 |
| `SRS-GUARDIAN-*` | Guardian Agent | ガバナンス・コンプライアンス監視 |
| `SRS-SHERLOCK-*` | Sherlock Agent | コード解析・診断推論 |
| `SRS-SENTINEL-*` | Sentinel Agent | セキュリティ監視・アラート |
| `SRS-AUTODEV-LOOP-001` | AutoDev Loop | 自律開発ループ |
| `SRS-COLLEGE-BRIDGE-001` | College Bridge | AIS College 連携 |
| `SRS-COUNCIL-BRIDGE-001` | Council Bridge | AGS Council 連携 |

### Finance Guild SRS コード (VCC ビルド対象)

| コード | サービス |
| ------ | -------- |
| `SRS-FIN-001` | smp-fin-api (REST API) |
| `SRS-FIN-002` | smp-fin-ws (WebSocket) |
| `SRS-FIN-003` | smp-fin-worker (Background worker) |
| `SRS-FIN-004` | smp-fin-pdf (PDF generation) |
| `SRS-FIN-005` | smp-fin-ai (AI inference) |

### OAD Reflex パターンコード

| コード | 内容 |
| ------ | ---- |
| `F924` | テナント分離 (RLS) 欠如 → 自動修正 |
| `F950` | Stripe アカウント不一致 |
| `F960` | 冪等キー強制欠如 |

### Stagger Chain パターンコード (MS-8)

| コード | 内容 |
| ------ | ---- |
| `F980` | Implementation drift → workhorse→premium 昇格 |
| `F981` | Quality regression → 再評価・再生成 |
| `F982` | Pipeline halt → フォールバック即時返却 |
| `F983` | Evolution stall → heavy (Opus) 強制解決 |
| `F984` | College convergence failure → AIS College エスカレーション |

---

## 4. TaskIR — 13ブロック仕様

全タスク定義 (`.sake` / SRS コード) に以下の13ブロックを含める。

| # | ブロック名 | 型 | 説明 |
| - | --------- | -- | ---- |
| 1 | `task_name` | str | タスク識別子 (PascalCase) |
| 2 | `purpose` | str | 1文でタスクの目的を記述 |
| 3 | `inputs` | List[str] | 入力データ・パラメーター一覧 |
| 4 | `outputs` | List[str] | 出力データ・アーティファクト一覧 |
| 5 | `preconditions` | List[str] | 実行前に満たすべき条件 |
| 6 | `postconditions` | List[str] | 実行後に保証される状態 |
| 7 | `algorithm` | str | 処理手順の自然言語記述 |
| 8 | `pseudocode` | List[str] | 疑似コードステップ一覧 |
| 9 | `error_handling` | List[str] | エラーケースと対処 |
| 10 | `test_spec` | List[str] | テストケース一覧 |
| 11 | `complexity` | str | 時間・空間計算量 |
| 12 | `dependencies` | List[str] | 依存モジュール・ENV 変数 |
| 13 | `security` | List[str] | セキュリティ考慮事項 |

---

## 5. CAPS Profile — グレード定義

`CitadelHealthSnapshot.code.caps_grade` と `VCCSakeReader.to_health_grade()` で使用。

| Grade | trust_score 範囲 | 意味 |
| ----- | --------------- | ---- |
| `T1` | ≥ 0.90 | 最高信頼 |
| `T2` | ≥ 0.75 | 高信頼 |
| `T3` | ≥ 0.60 | 標準 |
| `T4` | ≥ 0.40 | 要注意 |
| `T5` | < 0.40 | 低信頼 |

---

## 6. プロジェクト規約

### Python コーディング規約

1. `from __future__ import annotations` を全ファイル先頭に記載
2. 外部 API 呼び出しは `if env_var is None: return None` の graceful no-op を実装
3. 書き込み系関数は `dry_run: bool = True` パラメーターを持つ
4. `logger = logging.getLogger(__name__)` を使用（print 禁止）
5. 型ヒントは `Any` より具体的な型を優先

### テスト規約

1. テストファイルは `tests/test_{module_name}.py` の命名規則
2. `conftest.py` で共有フィクスチャを定義
3. 外部 API 依存は `unittest.mock` でモック化
4. `dry_run=True` のテストは credentials 不要で pass すること

### NATS イベント規約

- Citadel Lite **が発行する** subject: `citadel.oad.mission.dispatched`, `citadel.test.completed`
- **発行しない** subject: `citadel.vcc.build.pause/resume` (loop_orchestrator 専用)
- 全メッセージは `CitadelNATSEnvelope` でラップして内部ログに記録

### ENV 変数規約

- 全 credentials は環境変数で管理 (ハードコード禁止)
- 未設定時は graceful no-op (エラー発生禁止)
- `env_param_list.txt` が変数名の正典

---

## 7. CGRF 監査

```bash
# 全モジュールの 4 フィールド準拠確認 (non-strict)
python tools/cgrf_audit.py --report

# strict モード (violations > 0 で exit 1)
python tools/cgrf_audit.py --strict

# JSON 出力
python tools/cgrf_audit.py --report --format json > cgrf_report.json
```

CI では `.gitlab-ci.yml` / `.github/workflows/ci.yml` の `cgrf-compliance-check` ジョブが自動実行。

---

## 8. ブランチ戦略

```
main                ← 安定版
feat/vcc-oad-*      ← VCC/OAD/Perplexity 統合 feature ブランチ
feat/ms-c*          ← SMP/CGRF 関連マイルストーン
kohei/*             ← 個人作業ブランチ
```

PR はすべて `main` → `feat/*` の方向で作成。squash merge 推奨。
