# Citadel Lite × VCC × OAD × Perplexity — Integration Blueprint v9.0

> **v1.0** 2026-02-28 — Initial blueprint (VCC definition unknown)
> **v2.0** 2026-03-02 — Upgraded with VCC/CRP/OAD docs from `docs/notion_exports/`
> **v3.0** 2026-03-03 — 評価フィードバック統合: 役割分離・テスト責務明確化・スコア命名統一・NATSエンベロープ・DBスキーマ更新
> **v4.0** 2026-03-04 — pause/resume 発行制限の擬似コード修正・correlation_id nullable 化・ROADMAP 整合
> **v5.0** 2026-03-04 — CGRF v3.0 _EXECUTION_ROLE 追加・REFLEX 5ステージと OAD の関係明記・外部 NATS ストリーム補足・参照ドキュメント更新
> **v6.0** 2026-03-04 — Nemesis Defense System 統合採用・MS-B1〜B3 追加・CITADEL_NEMESIS / CITADEL_RED_TEAM ストリーム追記・Nemesis ENV 変数追加
> **v7.0** 2026-03-04 — ECS/NATS reconnection 設定追加・新 JetStream ストリーム (VOICE_EVENTS / INFRA_OPS / GOV_AUDIT) + 新 Subject (governance / infra / dlq)・Stagger Chain F980〜F984 パターン定義・本番 NATS URL (ECS vs VPS)・Perplexity Gap G4/G5 記載
> **v8.0** 2026-03-05 — SMP (Software Module Profile) 評価統合: CGRF CLAUDE.md + Notion SMP レジストリ DB + VCCSakeReader + CAPS grade 統合 (MS-C1〜C3)・スコープ外 F941/F977/F991/F999 明記
> **v9.0** 2026-03-06 — 全マイルストーン実装完了: MS-C1〜C3 + MS-A1〜A7 + MS-B1〜B3 の全テスト通過 (177 tests)。VCCSakeReader・DiagnosticsLoop・DatadogAdapter・NemesisInspector/Honeypots/Oracle・SMP Notion Sync・OrchestratorV3 Wire-in・Integrated Demo Run すべて実装・テスト済み。

---

## 用語定義

| 略語                    | 正式名称                                | 実行形態          | 役割                                                                      |
| --------------------- | ----------------------------------- | ------------- | ----------------------------------------------------------------------- |
| **VCC**               | Virtual Construction Crew           | 外部 LLM エージェント | Finance Guild の5マイクロサービスを自律構築する                                         |
| **CRP**               | Cycle Report Protocol               | VCC内部         | VCCビルドサイクルを追跡・記録。Notionへ8セクションレポートを投稿し、NATS へイベントを発行する                  |
| **OAD**               | Oracle Augmented Diagnostics        | 外部常駐 (3リグ)    | Reflex Engine による自動修正と Cognition Loop (L1/L2/L3 3層分析)                   |
| **Perplexity Loop**   | Perplexity Control Loop v2          | 外部常駐          | インフラ・収益・パイプラインの外部診断ループ（READ→RAG→THINK→WRITE）                            |
| **VCC Bridge**        | CRP ↔ Perplexity Bridge (Phase 2.1) | NATS 経由       | VCC/CRP と Perplexity の双方向イベント連携                                         |
| **Loop Orchestrator** | loop_orchestrator.py                | **外部常駐プロセス**  | VCC・Perplexity・OAD の3ループを購読し go/no-go を評価。`pause`/`resume` の**唯一の発行者**  |
| **OrchestratorV3**    | src/orchestrator_v3.py              | **リクエスト都度起動** | Citadel Lite の1オーダー処理器。Adapter 経由で各システムを呼び出す。pause/resume は発行しない（購読のみ可） |

---

## System Overview

### プロセス責務の分離

| プロセス                   | 起動形態                    | pause/resume | mission dispatch |
| ---------------------- | ----------------------- | ------------ | ---------------- |
| `loop_orchestrator.py` | 外部常駐 (systemd/ECS)      | **発行者**      | —                |
| `OrchestratorV3`       | リクエスト都度 (Citadel Lite内) | 購読のみ         | **発行者**          |

```
【外部常駐プロセス群】
  VCC (vcc_cycle_reporter) ──publish──► citadel.vcc.cycle.completed ──►┐
  Perplexity Loop          ──publish──► citadel.diagnostic.completed ──►┤
  OAD (Reflex/Cognition)   ──publish──► citadel.oad.*               ──►┤
                                                                        │
                              ┌─────────────────────────────────────────┘
                              ▼
                     NATS JetStream (Stream: VCC_BRIDGE)
                              │
                   ┌──────────┴──────────┐
                   ▼                     ▼
          loop_orchestrator.py     OrchestratorV3 (Citadel Lite)
          [外部常駐 / go-no-go]    [1オーダー処理器]
          evaluate_go_no_go()      ├─ VCC Adapter  (CRP消費・ミッション依頼)
          → pause/resume 発行      ├─ OAD Adapter  (Reflex・ミッション配信)
                   │               └─ Perplexity Adapter (診断ループ)
                   ▼
          Supabase: vcc_loop_state
          (loop_source: crp/perplexity/orchestrator)

【Citadel Lite 内部フロー】
  Orders UI / process_loop.py
          │
          ▼
  OrchestratorV3
  ├─ READ  : VCCAdapter.get_latest_crp() + PerplexityAdapter.run() + OADAdapter.signals()
  ├─ THINK : merge_health() → CitadelHealthSnapshot
  ├─ BUILD : VCCAdapter.build() → wait citadel.vcc.cycle.completed
  ├─ TEST  : ExecutionRunner.run_tests() → publish citadel.test.completed
  └─ REPAIR: OADAdapter.dispatch_mission() → wait citadel.oad.mission.completed
```

---

## コンポーネント詳細

### VCC (Virtual Construction Crew)

VCC は Finance Guild の5マイクロサービスを自律構築する LLM エージェント。

| サービス             | ポート  | 役割                    |
| ---------------- | ---- | --------------------- |
| `smp-fin-api`    | 8093 | REST API (請求書・見積・支払い) |
| `smp-fin-ws`     | 8094 | WebSocket (リアルタイム通知)  |
| `smp-fin-worker` | —    | バックグラウンドワーカー          |
| `smp-fin-pdf`    | 8095 | PDF 生成                |
| `smp-fin-ai`     | 8096 | AI 生成・推薦              |

**ビルドフェーズ:**

- Phase 0: Foundation (DB・ミドルウェア・フォルダ構造) ✅
- Phase 1: P0 Core (9ルーター中1.8完了) 🟡
- Phase 2: P1 Features (見積・PDF・税・Xero・検索・Email) 🔜
- Phase 3: P2 Features (AI・レポート・定期課金・クレジット) 🔜
- Phase 4: P3 Features (ECSデプロイ・署名・マルチ通貨) 🔜
- Phase 2.0: CRP ハードニング ✅ 設計済
- Phase 2.1: VCC Bridge (CRP ↔ Perplexity NATS) ✅ 設計済
- Phase 2.5: OAD 統合 ✅ 設計済

### CRP (Cycle Report Protocol)

CRP は VCC のビルドサイクルを8セクションで記録し、Notion に投稿後 NATS イベントを発行する。

**CRP ID 形式:** `VCC-FIN-YYYYMMDD-HHMM`

**8セクション:**

1. Cycle Header (cycle_id, guild, phase, crp_version, commit range)
2. What Was Built (SRS コード × ステータス絵文字)
3. Guardrails Compliance (セキュリティ・アーキテクチャ・整合性ルール — 重大違反ゼロ必須)
4. Flags & Questions (オペレーターレビュー待ち事項)
5. Drift Report (仕様↔実装の差分)
6. Next Cycle Intent (次回 SRS コード・フェーズ)
7. Health Metrics (テスト数・Notion同期・NATS状態・Perplexity診断フィードバック)
8. Diff Check (3レイヤー差分検証)

**CRP バージョン:**

- v1.0: 基本8セクション
- v2.0: スキーマ検証・トレンド追跡・SLA準拠・ガードレール強化 (FIX-001〜008)
- v2.1: Perplexity Bridge (BRIDGE-001〜009) — §7.4 に診断結果を注入
- v2.5: OAD 統合 (OAD-001〜009)

### OAD (Oracle Augmented Diagnostics)

3リグ分散で動作する自律診断・自動修正システム。

**Reflex Engine 対応パターン:**

| パターンコード | 内容              |
| ------- | --------------- |
| F924    | テナント分離 (RLS) 欠如 |
| F950    | Stripe アカウント不一致 |
| F960    | 冪等キー強制欠如        |

**Cognition Loop (rig2):**

- READ: Terraformステート・Linearイシュー・GitLab CIログ・Supabaseスキーマ・Notionブループリント
- THINK: L1(Perplexity) + L2(Azure OpenAI) + L3(AWS Bedrock) の3層分析
- WRITE: GitLab MR・Linearイシュー・Supabaseログ・Notionレポート

**Reflex Engine の設計ベース (REFLEX-System-Spec-v1.0):**

OAD Reflex Engine は REFLEX 5ステージパイプラインの実装。F924/F950/F960 は RESPOND ステージのパターンテンプレート。

| REFLEX ステージ | OAD 内の対応                                            |
| ----------- | --------------------------------------------------- |
| OBSERVE     | GitLab CI失敗・Datadog アラートを Signal として取得              |
| DIAGNOSE    | ルート原因分析 (F924/F950/F960 パターン照合)                     |
| RESPOND     | コードパッチ自動生成 (F924=RLS追加, F950=Stripe修正, F960=冪等キー追加) |
| VERIFY      | Canary デプロイ + メトリクス監視                               |
| LEARN       | パターンライブラリ更新 (AIS College へ格納)                       |

> Citadel Lite は OAD Adapter 経由で外部から呼び出すのみ。REFLEX 内部ステージは OAD が管理する。

---

## NATS JetStream 構成

**Stream:** `VCC_BRIDGE`

- max_msgs: 5000
- retention: 30日
- storage: file
- Consumer: `vcc-bridge-consumer` (durable, explicit ack, 30s ack-wait, max 5 redeliveries)

> **外部システムが使用するストリーム（Citadel Lite は直接管理しない）:**
> 
> | Stream                   | 管理元                            | 主要 Subject                                                                 | retention          | Citadel Lite との関係                       |
> | ------------------------ | ------------------------------ | -------------------------------------------------------------------------- | ------------------ | --------------------------------------- |
> | `REFLEX_EVENTS`          | OAD (REFLEX Engine)            | `reflex.event.*`, `reflex.fix.*`                                           | —                  | OAD Adapter 経由で間接参照                     |
> | AGS 内部                   | OrchestratorV3 (Phase 24 統合済み) | `ags.verdict.*`                                                            | —                  | Phase 24 で統合済み・購読のみ                     |
> | `CITADEL_NEMESIS`        | Nemesis (L1–L5)                | `citadel.nemesis.threat.*`, `citadel.nemesis.l2.*`, `citadel.nemesis.l3.*` | —                  | L2/L3 Adapter 経由で参照 (NEMESIS_ENABLED 時) |
> | `CITADEL_NEMESIS_ALERTS` | Nemesis Oracle                 | `citadel.nemesis.alert.*`                                                  | —                  | 重要アラート購読のみ                              |
> | `CITADEL_RED_TEAM`       | Nemesis Red Team               | `citadel.redteam.scan.*`, `citadel.redteam.scorecard.*`                    | —                  | 参照のみ (MS-B3 以降)                         |
> | `VOICE_EVENTS`           | VCC / AGS                      | `citadel.voice.*`                                                          | **24h**            | 音声イベント購読のみ                              |
> | `INFRA_OPS`              | OAD / Loop Orchestrator        | `citadel.infra.*`                                                          | **7d**             | インフラ操作ログ購読のみ                            |
> | `GOV_AUDIT`              | AGS Constitutional Council     | `citadel.governance.*`                                                     | **90d, 3-replica** | ガバナンス監査ログ参照のみ                           |

**Subject 一覧:**

| Subject                           | 発行者                        | 購読者                               | 内容                               |
| --------------------------------- | -------------------------- | --------------------------------- | -------------------------------- |
| `citadel.vcc.cycle.completed`     | vcc_cycle_reporter (VCC)   | loop_orchestrator, OrchestratorV3 | CRP サイクル完了（vcc_test_passed 含む）   |
| `citadel.vcc.build.pause`         | **loop_orchestrator のみ**   | VCC / Citadel Lite                | ビルド一時停止                          |
| `citadel.vcc.build.resume`        | **loop_orchestrator のみ**   | VCC / Citadel Lite                | ビルド再開                            |
| `citadel.diagnostic.completed`    | perplexity_control_loop_v2 | loop_orchestrator, OrchestratorV3 | Perplexity 診断完了（health_score 含む） |
| `citadel.oad.reflex.applied`      | OAD Reflex Engine          | loop_orchestrator                 | 自動修正適用                           |
| `citadel.oad.cognition.completed` | OAD Cognition Loop         | loop_orchestrator                 | 認知サイクル完了                         |
| `citadel.oad.mission.dispatched`  | **OrchestratorV3**         | OAD                               | OAD ミッション配信（Citadel Lite 発行）     |
| `citadel.oad.mission.completed`   | OAD                        | OrchestratorV3                    | ミッション結果                          |
| `citadel.test.completed`          | **OrchestratorV3**         | loop_orchestrator                 | Citadel Lite の検証テスト結果            |
| `citadel.governance.*`            | AGS Constitutional Council | loop_orchestrator                 | ガバナンスイベント (Stream: `GOV_AUDIT`)  |
| `citadel.infra.*`                 | OAD / Loop Orchestrator    | loop_orchestrator                 | インフラ操作イベント (Stream: `INFRA_OPS`) |
| `citadel.dlq.>`                   | NATS DLQ                   | loop_orchestrator                 | Dead Letter Queue — 配信失敗メッセージ再処理 |

---

## Nemesis Defense System

外部セキュリティ防御システム。6層 + Red Team で構成し、Citadel Lite は `NEMESIS_ENABLED=true` 時に FastAPI `main.py` へ middleware / routes をマウントして統合する。

### 6層 + Red Team アーキテクチャ

| 層   | 名称         | 主要ファイル                                                                          | 実装状況    | 役割                                                             |
| --- | ---------- | ------------------------------------------------------------------------------- | ------- | -------------------------------------------------------------- |
| L1  | Perimeter  | `nemesis_firewall.nft`                                                          | ⚠️ インフラ | nftables + CrowdSec IP ブロック                                    |
| L2  | Inspector  | `middleware/nemesis_inspector.py`                                               | ✅ 実装可   | AI ファイアウォール middleware (SQLi / XSS / プロンプトインジェクション検出)          |
| L3  | Hunter     | `routes/nemesis_honeypots.py`                                                   | ✅ 実装可   | ハニーポット + 自動ブラックリスト                                             |
| L4  | Oracle     | `services/nemesis_oracle.py`, `nemesis_retrain.py`, `nemesis_geo_aggregator.py` | ⚠️ 設計のみ | ML 分類器 + GeoIP 集約 + 自動再学習                                      |
| L5  | Shield     | `playbooks/shield-deploy.yaml`, `roles/shield-*`                                | ❌ 未整備   | Ansible ロール (NATS TLS / egress / probe logger / canary tokens) |
| L6  | Compliance | `.semgrep/`, `terraform/cloudflare_waf.tf`, `.gitlab-ci.yml`                    | ❌ 未整備   | SAST / DAST / Cloudflare WAF / ペンテスト                           |
| RT  | Red Team   | `services/redteam/`                                                             | ✅ 設計完了  | 自律 Purple Team 脆弱性スキャナー (8モジュール)                               |

### Citadel Lite 統合ポイント

Nemesis は `src/api/main.py` に以下のブロックで有効化する（`NEMESIS_ENABLED` ENV フラグで制御）:

```python
# ============================================================
# Nemesis Defense System — mount block
# ============================================================
import os

if os.getenv("NEMESIS_ENABLED") == "true":
    # L2 Inspector middleware
    from middleware.nemesis_inspector import NemesisInspectorMiddleware
    app.add_middleware(NemesisInspectorMiddleware)

    # L6 CORS hardening
    from middleware.cors_hardening import add_cors
    add_cors(app)

    # L4 Nemesis admin API
    from routes.nemesis_api import router as nemesis_router
    app.include_router(nemesis_router)

    # L3 Honeypots
    from routes.nemesis_honeypots import honeypot_router
    app.include_router(honeypot_router)
```

### Nemesis NATS ストリーム

| Stream                   | 管理元              | 主要 Subject                                                                                                                 | 用途                     |
| ------------------------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| `CITADEL_NEMESIS`        | Nemesis (L1–L5)  | `citadel.nemesis.threat.*`, `citadel.nemesis.l2.blocked`, `citadel.nemesis.l3.honeypot_hit`, `citadel.nemesis.l4.oracle.*` | 防衛イベント全般               |
| `CITADEL_NEMESIS_ALERTS` | Nemesis Oracle   | `citadel.nemesis.alert.*`                                                                                                  | 重要アラート (高スコア脅威・バイパス検出) |
| `CITADEL_RED_TEAM`       | Nemesis Red Team | `citadel.redteam.scan.*`, `citadel.redteam.campaign.*`, `citadel.redteam.scorecard.*`                                      | Red Team スキャン結果        |

> これらは Citadel Lite が直接管理しない外部ストリーム。L2/L3 adapter 経由で参照する。

### Nemesis Supabase テーブル

| Migration ファイル                       | 主要テーブル                                                       | 層   |
| ------------------------------------ | ------------------------------------------------------------ | --- |
| `migrations/20260226_nemesis.sql`    | `nemesis_events`, `nemesis_threats`, `nemesis_honeypot_hits` | L4  |
| `migrations/20260226_shield.sql`     | `pii_erasure_requests`, `probe_logs`, `canary_tokens`        | L5  |
| `migrations/20260226_compliance.sql` | `pentest_findings`, `security_policies`, `risk_register`     | L6  |
| `migrations/20260226_redteam.sql`    | `rt_campaigns`, `rt_scans`, `rt_scorecards`                  | RT  |

### 実装フェーズ

| フェーズ   | 内容                                              | 実装可否      |
| ------ | ----------------------------------------------- | --------- |
| MS-B1  | L2 Inspector middleware + CORS hardening        | ✅ 完了      |
| MS-B2  | L3 Hunter honeypots                             | ✅ 完了      |
| MS-B3  | L4 Oracle + Datadog + nemesis_api + NATS stream | ✅ 完了      |
| MS-B4+ | L5 Shield + L6 Compliance + Red Team            | ❌ インフラ整備後 |

---

## Stagger Chain (MS-8)

MS-8 で実装するティアード推論パイプライン。Citadel Lite 内部の品質自己修正システムで、OAD Reflex Engine の F924/F950/F960 (外部システム) とは独立した設計。

> **現状**: `CONFIDENCE_WRAPPER` JSON 形式の衝突問題解決待ち。`perplexity_control_loop_v2.py` の `vault_loader` 依存を分離後に着手 (Out-of-Scope / MS-8)。

### 推論ティア構成 (triage → workhorse → premium → heavy)

| ティア         | モデル        | 役割                     |
| ----------- | ---------- | ---------------------- |
| `triage`    | **Haiku**  | 初期トリアージ・高速判定・ルーティング    |
| `workhorse` | **Sonnet** | 主力処理・標準品質              |
| `premium`   | **Sonnet** | 高品質処理・精密分析 (設定強化版)     |
| `heavy`     | **Opus**   | 最高品質・複雑問題解決・最終エスカレーション |

**品質ゲート**: `batch_audit.py` — 各ティア出力を審査し、品質基準未達時に上位ティアへエスカレーション。

### Stagger Chain Reflex パターン (F980〜F984)

> OAD の F924/F950/F960 は外部 OAD システムが管理。F980〜F984 は Citadel Lite 内 `stagger_chain.py` が管理する独立ループ。

| パターンコード | 内容                                         | エスカレーション先                  |
| ------- | ------------------------------------------ | -------------------------- |
| F980    | Implementation drift (実装ドリフト)              | `workhorse` → `premium` 昇格 |
| F981    | Quality regression (品質劣化)                  | 前ティア出力を再評価・再生成             |
| F982    | Pipeline halt (パイプライン停止)                   | フォールバック応答を即時返却             |
| F983    | Evolution stall (進化停止)                     | `heavy` (Opus) で強制解決       |
| F984    | College convergence failure (College 収束失敗) | AIS College へエスカレーション      |

### 主要ファイル (MS-8)

| ファイル                          | 内容                                       | EXECUTION_ROLE    |
| ----------------------------- | ---------------------------------------- | ----------------- |
| `src/stagger_chain.py`        | `StaggerChain` — ティアード推論エントリポイント         | `AGENT`           |
| `src/batch_audit.py`          | `BatchAudit` — 各ティア出力の品質ゲート              | `BACKEND_SERVICE` |
| `tests/test_stagger_chain.py` | Stagger Chain + F980〜F984 Reflex パターンテスト | —                 |

---

## Interfaces / Contracts

### NATS イベントペイロード

```json
// citadel.vcc.cycle.completed — CycleCompletedPayload
// ※ vcc_test_* = Finance Guild コードベースのユニットテスト（CRP が実行）
{
  "cycle_id": "VCC-FIN-20260302-1200",
  "guild": "FIN",
  "phase": "P1",
  "crp_version": "2.1",
  "guardrail_pass": true,
  "drift_clean": true,
  "vcc_test_passed": 54,
  "vcc_test_failed": 0,
  "srs_codes_touched": {"SRS-FIN-004": "✅ built"},
  "health_status": "healthy",
  "sla_compliant": true,
  "notion_page_id": "abc123",
  "timestamp": "2026-03-02T12:00:00Z"
}
```

```json
// citadel.test.completed — TestCompletedPayload
// ※ Citadel Lite の ExecutionRunner が実行する検証テスト結果
{
  "order_id": "ORD-2026-03-02-0001",
  "crp_cycle_id": "VCC-FIN-20260302-1200",
  "all_success": true,
  "steps_total": 3,
  "steps_passed": 3,
  "steps_failed": 0,
  "simulated": false,
  "timestamp": "2026-03-02T12:20:00Z"
}
```

```json
// citadel.diagnostic.completed — DiagnosticCompletedPayload
{
  "diag_id": "DIAG-20260302-1210",
  "health_grade": "HEALTHY",
  "health_score": 87,
  "blockers": [],
  "recommendations": ["Rotate GitLab token before next cycle"],
  "sources_read": ["datadog", "posthog", "supabase", "notion", "gitlab"],
  "l3_verdict": "APPROVED",
  "pipeline_pass_rate": 0.95,
  "nats_connections": 3,
  "mrr_cents": 125000,
  "triggered_by": "crp_cycle",
  "crp_cycle_id": "VCC-FIN-20260302-1200",
  "timestamp": "2026-03-02T12:10:00Z"
}
```

```json
// citadel.oad.mission.dispatched — MissionDispatchPayload
{
  "mission_id": "MISSION-20260302-001",
  "rig_target": "rig2",
  "mission_type": "cognition",
  "payload": {"focus": "RLS drift detection"},
  "priority": "high",
  "timestamp": "2026-03-02T12:05:00Z"
}
```

```json
// citadel.oad.reflex.applied — ReflexAppliedPayload
{
  "reflex_id": "REFLEX-20260302-001",
  "rig": "rig1",
  "pattern_code": "F924",
  "file_path": "src/router_invoices.py",
  "fix_description": "Added RLS policy for tenant_id isolation",
  "before_hash": "abc1234",
  "after_hash": "def5678",
  "timestamp": "2026-03-02T12:06:00Z"
}
```

### Citadel Lite 内部 NATS エンベロープ (CitadelNATSEnvelope)

> 上流システム（VCC/OAD）のペイロードは**変更しない**。
> Citadel Lite の `NATSBridgeClient` がメッセージ受信時にアダプター層でラップし、
> 内部監査ログと Datadog トレースで `correlation_id` を使用する。
> 上流への後方互換性への影響: **ゼロ**。

```python
# src/integrations/nats/bridge_client.py 内部処理
@dataclass
class CitadelNATSEnvelope:
    schema: str          # "citadel.event.v1" — 固定
    event_id: str        # Citadel Lite が付与する UUID (uuid4)
    event_type: str      # NATS subject (例: "citadel.vcc.cycle.completed")
    correlation_id: Optional[str]  # 優先順: order_id → cycle_id → diag_id → None
    received_at: str     # 受信タイムスタンプ (ISO 8601)
    nats_seq: int        # 上流の NATS sequence number (ack.seq)
    payload: dict        # 生ペイロード (変更しない)
```

```json
// 内部ログ・Datadog トレース用エンベロープ例
// correlation_id 優先順: order_id (注文起点) → cycle_id (CRP起点) → diag_id (定期診断起点) → null
{
  "schema": "citadel.event.v1",
  "event_id": "evt-550e8400-e29b-41d4-a716-446655440000",
  "event_type": "citadel.vcc.cycle.completed",
  "correlation_id": "ORD-2026-03-03-0001",
  "received_at": "2026-03-03T12:00:05Z",
  "nats_seq": 1842,
  "payload": {
    "cycle_id": "VCC-FIN-20260303-1200",
    "vcc_test_passed": 54,
    "..."  : "..."
  }
}
```

### Citadel Lite 内部コントラクト (既存ブループリント継承)

```json
// Citadel Lite -> VCC Adapter : BuildRequest
{
  "schema": "vcc.build_request.v1",
  "order_id": "ORD-2026-03-02-0001",
  "repo": "citadel_lite_repo",
  "target": {
    "branch": "feat/demo",
    "module": "src",
    "goal": "Implement diagnostics UI flow"
  },
  "constraints": {
    "timebox_minutes": 30,
    "no_large_refactors": true,
    "touch_points": ["src/orchestrator_v3.py", "src/integrations/*"]
  },
  "context": {
    "user_intent": "demo integration loop",
    "risk_level": "medium"
  }
}
```

```json
// VCC Adapter -> Citadel Lite : BuildResult
{
  "schema": "vcc.build_result.v1",
  "order_id": "ORD-2026-03-02-0001",
  "status": "ok",
  "artifacts": {
    "patches": ["a1b2c3.diff"],
    "files_changed": ["src/integrations/vcc/client.py"]
  },
  "crp_cycle_id": "VCC-FIN-20260302-1200",
  "notes": "Minimal adapter added, no refactor",
  "metrics": {
    "build_time_ms": 18420,
    "build_checks_passed": true
  }
  // ※ テスト実行責務は VCC (vcc_test_*) と Citadel Lite (citadel.test.completed) が別々に持つ
}
```

```json
// Citadel Lite -> OAD Adapter : RepairRequest
{
  "schema": "oad.repair_request.v1",
  "order_id": "ORD-2026-03-02-0001",
  "build_result": {"status": "ok", "files_changed": ["src/integrations/vcc/client.py"]},
  "test_failures": [
    {"name": "test_full_governance_loop", "error": "ImportError: ..."}
  ],
  "signals": [
    {
      "signal_id": "sig-001",
      "source": "gitlab",
      "event_type": "pipeline_failed",
      "signal_class": "technical",
      "priority": "high",
      "should_trigger_reflex": true
    }
  ]
}
```

```json
// Citadel Lite -> Perplexity Loop Adapter : DiagnosticsRequest
{
  "schema": "pplx.diagnostics_request.v1",
  "order_id": "ORD-2026-03-02-0001",
  "windows": {"dd_hours": 6, "ph_days": 14},
  "targets": ["gitlab", "supabase", "notion", "datadog", "posthog", "stripe", "metabase"],
  "mode": "dry_run",
  "context": {"project_id": 75, "team_id": "CNWB"}
}
```

### 統合健全性スナップショット (CitadelHealthSnapshot)

スコア命名規則:

- `health_grade` / `health_score` — Perplexity Loop 出力そのまま（ソース: DiagnosticCompletedPayload）
- `overall_grade` / `overall_score` — 加重統合スコア（Pplx 40% + guardrail 20% + drift 15% + SLA 15% + services 10%）
- `vcc_test_*` — Finance Guild ユニットテスト数（ソース: CRPCyclePayload）
- ~~`perplexity_score`~~ — 廃止。`health_score` を参照のこと

```json
{
  "snapshot_id": "HEALTH-20260302-1200",
  "timestamp": "2026-03-02T12:00:00Z",
  "source": "merged",
  "overall_grade": "HEALTHY",
  "overall_score": 87,
  "services": [
    {"name": "smp-fin-api", "port": 8093, "status": "up", "latency_p95_ms": 210}
  ],
  "infrastructure": {
    "nats_connections": 3,
    "cpu_pct": 42,
    "memory_pct": 61
  },
  "code": {
    "pipeline_pass_rate": 0.95,
    "vcc_test_passed": 54,
    "vcc_test_failed": 0,
    "coverage_pct": 78
  },
  "revenue": {
    "mrr_cents": 125000,
    "active_subscriptions": 38
  },
  "crp_cycle_id": "VCC-FIN-20260302-1200",
  "guardrail_pass": true,
  "drift_clean": true,
  "sla_compliant": true,
  "diag_id": "DIAG-20260302-1210",
  "health_grade": "HEALTHY",
  "health_score": 87,
  "l3_verdict": "APPROVED",
  "go_no_go": "GO",
  "blockers": [],
  "recommendations": []
}
```

---

## Execution Loop (READ / THINK / WRITE / ASSESS / BLUEPRINT / BUILD / TEST)

```pseudo
function run_order(order):

  READ:
    // CRP 最新サイクル状態を NATS/Supabase から取得
    crp_state    = VCCAdapter.get_latest_crp(from=vcc_loop_state)
    // Perplexity 診断 (DD/PH/SB/Notion/GitLab/Stripe/Metabase)
    telemetry    = PerplexityLoop.read_sources(targets)
    // OAD シグナル (GitLab pipeline_failed など)
    oad_signals  = OADAdapter.pull_latest_signals()
    // 健全性スナップショット統合
    health       = merge_health(crp_state, telemetry, oad_signals)

  THINK:
    diagnosis    = PerplexityLoop.think(health)
    decision     = OrchestratorV3.decide(order, diagnosis)
    // CRITICAL / DEGRADING なら Supabase vcc_loop_state に NO-GO を書き込む
    // → loop_orchestrator がポーリングして citadel.vcc.build.pause を発行する（唯一の発行者）
    if health.overall_grade in ("CRITICAL", "DEGRADING") and health.overall_score < 60:
      SupabaseStore.upsert_loop_state({
        "loop_source": "orchestrator",
        "cycle_id": health.crp_cycle_id,
        "go_no_go": "NO-GO",
        "blocking_reasons": ["health_gate_failed"],
      })

  WRITE:
    PerplexityLoop.write_reports(diagnosis)   // Notion + Linear + GitLab
    OrchestratorV3.audit(decision)

  ASSESS:
    risk = OrchestratorV3.assess_risk(decision)
    DatadogAdapter.emit_metric("citadel.loop.risk", risk)
    Observability.emit_metrics(risk, loop="diagnostics")

  BLUEPRINT:
    if decision.requires_blueprint:
      blueprint = OrchestratorV3.generate_blueprint(order, diagnosis)
      NotionSearch.optional_find("VCC CRP blueprints")

  BUILD:
    build_result = VCCAdapter.build(blueprint or decision)
    // CRP サイクル完了イベントを NATS から購読して build_result に充填
    crp_event    = NATSBridge.wait_for("citadel.vcc.cycle.completed", timeout=60s)

  TEST:
    test_result = ExecutionRunner.run_tests(build_result)
    if test_result.failed:
      // OAD Reflex Engine を起動してパターン自動修正
      repair = OADAdapter.repair(build_result, test_result)
      // OAD ミッション完了を NATS から購読
      oad_result = NATSBridge.wait_for("citadel.oad.mission.completed", timeout=120s)
      Observability.emit_metrics(repair)
```

---

## Shared State Store (Supabase)

**Table: `public.vcc_loop_state`**

> 実際の SQL (`supabase/migrations/20260228_vcc_loop_state.sql`) に準拠。
> `loop_source` で crp/perplexity/orchestrator の3行が1サイクルに存在する設計（single-row ではない）。

| カラム                         | 型           | 値域 / 説明                                                     |
| --------------------------- | ----------- | ----------------------------------------------------------- |
| `id`                        | uuid        | PK (gen_random_uuid)                                        |
| `loop_source`               | text        | `"crp"` \| `"perplexity"` \| `"orchestrator"`               |
| `cycle_id`                  | text        | CRP サイクル ID (`VCC-FIN-YYYYMMDD-HHMM`)                       |
| `guild`                     | text        | ギルド識別子 (例: `"FIN"`)                                         |
| `phase`                     | text        | フェーズ (例: `"P1"`)                                            |
| `guardrail_pass`            | boolean     | CRP ガードレール合否                                                |
| `drift_clean`               | boolean     | CRP ドリフト検証合否                                                |
| `sla_compliant`             | boolean     | SLA 準拠フラグ                                                   |
| `vcc_test_passed`           | int         | Finance Guild ユニットテスト 合格数                                   |
| `vcc_test_failed`           | int         | Finance Guild ユニットテスト 失敗数                                   |
| `srs_codes_touched`         | jsonb       | 触れた SRS コード一覧                                               |
| `health_grade`              | text        | `"HEALTHY"` \| `"DEGRADING"` \| `"CRITICAL"` \| `"UNKNOWN"` |
| `health_score`              | int         | Perplexity 診断スコア (0–100)                                    |
| `l3_verdict`                | text        | Perplexity L3 判定テキスト                                        |
| `blockers`                  | jsonb       | ブロッカー一覧 (`[]`)                                              |
| `recommendations`           | jsonb       | 推奨事項一覧                                                      |
| `merged_grade`              | text        | 統合グレード (orchestrator が書く)                                   |
| `merged_score`              | int         | 統合スコア (加重平均)                                                |
| `go_no_go`                  | text        | `"GO"` \| `"NO-GO"` \| `"WARNING"`                          |
| `blocking_reasons`          | jsonb       | NO-GO の理由一覧                                                 |
| `notion_diagnostic_page_id` | text        | Perplexity 診断 Notion ページ ID                                 |
| `env`                       | text        | 環境識別子 (例: `"production"` / `"staging"`) ※Citadel Lite 追加列   |
| `created_at`                | timestamptz | 行作成日時                                                       |
| `expires_at`                | timestamptz | 自動削除日時 (90日後)                                               |

**インデックス:**

- `idx_vcc_loop_state_source` on `(loop_source)`
- `idx_vcc_loop_state_cycle` on `(cycle_id)`
- `idx_vcc_loop_state_created` on `(created_at DESC)`
- `idx_vcc_loop_state_grade` on `(health_grade)` WHERE `loop_source = 'perplexity'`

> **Citadel Lite 側 migration:** 既存テーブルに `env` 列を追加する migration を `src/integrations/nats/` に同梱する。

---

## Repository Plan (Minimal Scaffolding)

既存構造を踏襲し、thin adapter のみ追加。

### 新規ファイル

```
src/
├── contracts/
│   ├── orders.py               # BuildRequest, BuildResult (schema v1)
│   └── diagnostics.py          # RepairRequest/Result, DiagnosticsRequest/Report,
│                               # CitadelHealthSnapshot, Signal
├── integrations/
│   ├── vcc/
│   │   ├── __init__.py
│   │   ├── contracts.py        # src/contracts/ からの re-export
│   │   └── client.py           # VCCClient — build() / get_latest_crp()
│   ├── oad/
│   │   ├── __init__.py
│   │   ├── client.py           # OADClient — repair() / dispatch_mission()
│   │   └── signal_router.py    # OADSignalRouter — pull_latest_signals()
│   ├── perplexity/
│   │   ├── __init__.py
│   │   ├── control_loop_client.py      # PerplexityControlLoopClient — run()
│   │   └── action_executor_client.py   # PerplexityActionExecutor — execute()
│   └── notion_search.py        # (optional) NotionSearchClient — search()
├── modules/
│   └── diagnostics_loop.py     # DiagnosticsLoop — READ/THINK/WRITE/ASSESS
└── monitoring/
    └── datadog_adapter.py      # DatadogAdapter — emit_event() / emit_metric() / read_monitors()
```

### NATS Bridge (新規、tools/ 相当)

```
src/integrations/nats/
├── __init__.py
├── bridge_client.py            # NATSBridgeClient — publish() / subscribe() / wait_for()
└── schemas.py                  # Pydantic schemas: CycleCompletedPayload,
                                # DiagnosticCompletedPayload, ReflexAppliedPayload,
                                # MissionDispatchPayload, MissionCompletedPayload
```

### CGRF v3.0 モジュールヘッダー要件

全新規ファイルに以下を付与する (`blueprints/CGRF-v3.0-Complete-Framework.md` 準拠):

```python
_MODULE_NAME    = "module_name"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1                  # Tier 1 (DEVELOPMENT)
_EXECUTION_ROLE = "INTEGRATION"      # INTEGRATION | BACKEND_SERVICE | AGENT | ...
```

モジュール別 `_EXECUTION_ROLE` 対応:

| モジュール                                                                                          | `_EXECUTION_ROLE` |
| ---------------------------------------------------------------------------------------------- | ----------------- |
| `vcc/client.py`, `oad/client.py`, `perplexity/control_loop_client.py`, `nats/bridge_client.py` | `INTEGRATION`     |
| `modules/diagnostics_loop.py`                                                                  | `BACKEND_SERVICE` |
| `monitoring/datadog_adapter.py`                                                                | `INTEGRATION`     |

### 既存ファイル変更

| ファイル                     | 変更内容                                             |
| ------------------------ | ------------------------------------------------ |
| `src/orchestrator_v3.py` | DiagnosticsLoop hook + adapter injection (MS-A6) |
| `config/settings.yaml`   | `diagnostics_loop:` セクション追加                      |

---

## 環境変数

> 変数名は `env_param_list.txt` を正とする (2026-03-02 照合済み)

### NATS

| 変数              | 用途                 | デフォルト                   |
| --------------- | ------------------ | ----------------------- |
| `NATS_URL`      | NATS JetStream 接続先 | `nats://localhost:4222` |
| `NATS_USER`     | NATS 認証ユーザー        | (未設定=無認証)               |
| `NATS_PASSWORD` | NATS 認証パスワード       | (未設定=無認証)               |

> **本番 NATS URL 対応表:**
> 
> | 環境              | `NATS_URL` 値                     | 備考                             |
> | --------------- | -------------------------------- | ------------------------------ |
> | ECS (AWS)       | `nats://nats.citadel.local:4222` | ECS サービスディスカバリ経由 (VPC 内ルーティング) |
> | VPS (Hostinger) | `nats://147.93.43.117:4222`      | 直接 IP 接続・TLS 設定は L5 Shield 担当  |
> | ローカル開発          | `nats://localhost:4222`          | Docker / nats-server 直接起動      |

### OAD

| 変数                  | 用途                                         | デフォルト |
| ------------------- | ------------------------------------------ | ----- |
| `OAD_PAT`           | OAD 主認証 PAT（未設定時は `GITLAB_TOKEN` にフォールバック） | —     |
| `OAD_RIG_ID`        | OAD リグ識別子 (`rig1` / `rig2` / `rig3`)       | —     |
| `OAD_CYCLE_SECONDS` | OAD 認知サイクル間隔 (秒)                           | —     |
| `OAD_R1_GITLAB_PAT` | OAD Rig1 専用 GitLab PAT（プロジェクト75 / CNWB）    | —     |

### GitLab

| 変数                        | 用途                | デフォルト |
| ------------------------- | ----------------- | ----- |
| `GITLAB_TOKEN`            | GitLab API 汎用トークン | (既存)  |
| `GITLAB_TOKEN_AUTOMATION` | GitLab 自動化専用トークン  | (既存)  |

### Perplexity

| 変数             | 用途                | デフォルト |
| -------------- | ----------------- | ----- |
| `PPLX_API_KEY` | Perplexity API キー | —     |

### Datadog

| 変数           | 用途                          | デフォルト           |
| ------------ | --------------------------- | --------------- |
| `DD_API_KEY` | Datadog API キー              | —               |
| `DD_APP_KEY` | Datadog App キー（メトリクスクエリに必須） | —               |
| `DD_SITE`    | Datadog サイト                 | `datadoghq.com` |
| `DD_ENV`     | Datadog 環境タグ                | —               |

### Supabase / DB

| 変数                     | 用途           | デフォルト |
| ---------------------- | ------------ | ----- |
| `SUPABASE_URL`         | Supabase 接続先 | (既存)  |
| `SUPABASE_SERVICE_KEY` | Supabase 認証  | (既存)  |

### Notion

| 変数             | 用途                          | デフォルト |
| -------------- | --------------------------- | ----- |
| `NOTION_TOKEN` | Notion CRP レポート投稿・診断ページ書き込み | (既存)  |

### SMP (MS-C1〜C3)

| 変数                          | 用途                                                    | デフォルト            |
| --------------------------- | ----------------------------------------------------- | ---------------- |
| `NOTION_SMP_REGISTRY_DB_ID` | Notion SMP レジストリ DB ID (MS-C2 smp_notion_sync.py が使用) | —                |
| `CGRF_AUDIT_STRICT`         | `tools/cgrf_audit.py` strict mode。`true` で CI 失敗させる   | `false`          |
| `VCC_SAKE_PROFILE_DIR`      | `.sake` プロファイル配置ディレクトリ (MS-C3 VCCSakeReader が参照)      | `sake_profiles/` |

### Linear

| 変数               | 用途            | デフォルト |
| ---------------- | ------------- | ----- |
| `LINEAR_API_KEY` | Linear イシュー操作 | (既存)  |

### Nemesis

| 変数                         | 用途                                        | デフォルト   |
| -------------------------- | ----------------------------------------- | ------- |
| `NEMESIS_ENABLED`          | Nemesis 全体有効化フラグ (`true` で main.py にマウント) | `false` |
| `NEMESIS_ADMIN_TOKEN`      | `/api/nemesis/*` 管理 API 認証トークン            | —       |
| `NEMESIS_THREAT_THRESHOLD` | 脅威スコア遮断閾値 (0.0–1.0)。L2 Inspector が使用      | `0.7`   |
| `NEMESIS_QUARANTINE_TTL`   | 隔離 IP の有効期間 (秒)                           | `3600`  |
| `NEMESIS_CF_AUTO_BLOCK`    | Cloudflare 自動ブロック有効化 (L6)                 | `false` |
| `GEOIP_ACCOUNT_ID`         | MaxMind GeoIP アカウント ID (L4 Oracle が使用)    | —       |
| `GEOIP_LICENSE_KEY`        | MaxMind GeoIP ライセンスキー                     | —       |
| `ABUSEIPDB_KEY`            | AbuseIPDB API キー (L2 Inspector が使用)       | —       |
| `PII_ENCRYPTION_KEY`       | PII データ暗号化キー (L5 Shield が使用)              | —       |
| `CLOUDFLARE_API_TOKEN`     | Cloudflare WAF 管理 API トークン (L6)           | —       |
| `CLOUDFLARE_ZONE_ID`       | Cloudflare ゾーン ID (L6)                    | —       |

---

## Milestones (改訂版)

### MS-A1 — Contracts & NATS Schemas 定義 ✅ 完了

- `src/contracts/orders.py`: `BuildRequest`, `BuildResult` (`build_checks_passed` フィールド含む)
- `src/contracts/diagnostics.py`: `RepairRequest`, `RepairResult`, `DiagnosticsRequest`, `DiagnosticsReport`, `CitadelHealthSnapshot` (`overall_grade/score`、`health_grade/score`、`vcc_test_*`、`go_no_go` フィールド含む)、`Signal`
- `src/integrations/nats/schemas.py` (Pydantic):
  - `CycleCompletedPayload` (`vcc_test_passed/failed` に修正)
  - `DiagnosticCompletedPayload` (`health_grade`, `health_score`)
  - `ReflexAppliedPayload`
  - `MissionDispatchPayload`, `MissionCompletedPayload`
  - `TestCompletedPayload` (新規: Citadel Lite 検証テスト結果)
  - `BuildControlPayload` (新規: pause/resume)
  - `CitadelNATSEnvelope` (新規: 内部ラッパー、上流変更なし)
- `src/integrations/nats/migrations/add_env_column.sql`: `vcc_loop_state` に `env` 列を追加

### MS-A2 — Adapter Skeletons (dry_run=True 全 adapter 動作) ✅ 完了

- VCC Adapter: `build()` / `get_latest_crp()`
- OAD Adapter: `repair()` / `dispatch_mission()` / `pull_latest_signals()`
- Perplexity Adapter: `run()` (READ→THINK→WRITE→ASSESS) / `execute(actions)`
- NATS Bridge: `publish()` / `subscribe()` / `wait_for()` (nats.py を使用、未設定時はスタブ)
- NotionSearch: `search()` (optional)

**`NATSBridgeClient` 接続パラメーター (本番推奨値):**

```python
# src/integrations/nats/bridge_client.py
class NATSBridgeClient:
    # ECS / VPS 共通の接続設定
    CONNECTION_DEFAULTS = {
        "max_reconnect_attempts": -1,    # 無制限再接続 (障害時に永続再試行)
        "reconnect_time_wait": 2.0,      # 再接続基本待機 (秒)
        "max_reconnect_time_wait": 60.0, # 指数バックオフ上限 (秒)
        "ping_interval": 30,             # Ping 間隔 (秒)
        "max_outstanding_pings": 2,      # 未応答 Ping 上限 (超過で切断→再接続)
    }
```

> ECS 本番: `NATS_URL=nats://nats.citadel.local:4222` / VPS 本番: `NATS_URL=nats://147.93.43.117:4222`

### MS-A3 — Diagnostics Loop モジュール ✅ 完了

- `src/modules/diagnostics_loop.py`: `DiagnosticsLoop.run()` で4ステップを統括
- 健全性スナップショット (`CitadelHealthSnapshot`) の組み立てと verdict 判定
- health_grade が CRITICAL かつ score < 60 の場合に `vcc_loop_state` へ `go_no_go = "NO-GO"` を書き込み（pause 発行は loop_orchestrator に委譲）

### MS-A4 — OAD Repair Hook ✅ 完了

- `signal_router.py`: GitLab `pipeline_failed` / Datadog アラート → `Signal` に正規化
- テスト失敗時に `OADClient.dispatch_mission()` → NATS `citadel.oad.mission.dispatched`
- CRP §5 Drift Report に Reflex 修正を反映

### MS-A5 — Observability (Datadog + Prometheus) ✅ 完了

- `DatadogAdapter`: `emit_event()` / `emit_metric()` / `read_monitors()`
- Prometheus: 既存 `src/monitoring/metrics.py` に diagnostics_loop 用メトリクス追加
  - `citadel_diagnostics_loop_runs_total` (Counter, labels: verdict)
  - `citadel_health_score` (Gauge)
  - `citadel_nats_events_published_total` (Counter, labels: subject)

### MS-A6 — Orchestrator V3 Wire-in ✅ 完了

- `OrchestratorV3.__init__`: `diagnostics_loop` / `vcc_adapter` / `oad_adapter` を DI
- `_run_from_event_inner` 末尾に `_run_diagnostics_loop()` 追加
- `settings.yaml` の `diagnostics_loop.enabled=false` でデフォルトスキップ
- 既存テストへの影響ゼロを確認

### MS-A7 — Integrated Demo Run ✅ 完了

- `demo/events/ci_failed.sample.json` を1イベントとして一気通貫実行
- 生成物: `out/<id>/diagnostics_report.json`, `out/<id>/build_result.json`, `out/<id>/repair_result.json`
- dry_run=True で外部 API ゼロ呼び出しを確認

---

### MS-B1 — Nemesis L2 Inspector middleware ✅ 完了

- `middleware/nemesis_inspector.py`: FastAPI `NemesisInspectorMiddleware` — SQLi / XSS / SSRF / プロンプトインジェクション検出
- `middleware/cors_hardening.py`: L6 CORS ハードニング
- `src/api/main.py` に Nemesis マウントブロック追加 (`NEMESIS_ENABLED` ガード付き)
- CGRF Tier 1 ヘッダー付与 (`_EXECUTION_ROLE = "INTEGRATION"`)
- テスト: `tests/test_nemesis_inspector.py`

### MS-B2 — Nemesis L3 Hunter (Honeypots) ✅ 完了

- `routes/nemesis_honeypots.py`: FastAPI `honeypot_router` — 囮エンドポイント (`/admin`, `/.env`, `/wp-login.php` 等)
- Supabase: `nemesis_honeypot_hits` テーブル (migration: `20260226_nemesis.sql` の一部)
- NATS: `citadel.nemesis.l3.honeypot_hit` 発行
- テスト: `tests/test_nemesis_honeypots.py`

### MS-B3 — Nemesis L4 Oracle + Admin API ✅ 完了

- `services/nemesis_oracle.py`: ML 分類器 (FastText / sklearn ベース)
- `services/nemesis_retrain.py`: オンライン再学習
- `services/nemesis_geo_aggregator.py`: MaxMind GeoIP 集約 (`GEOIP_ACCOUNT_ID` / `GEOIP_LICENSE_KEY`)
- `routes/nemesis_api.py`: `/api/nemesis/health`, `/api/nemesis/dashboard/summary` 等
- `config/nats-nemesis.yaml`: `CITADEL_NEMESIS` + `CITADEL_NEMESIS_ALERTS` stream 定義
- `migrations/20260226_nemesis.sql`: `nemesis_events`, `nemesis_threats`, `nemesis_honeypot_hits` テーブル
- Datadog: L2/L3/L4 メトリクス (`nemesis.l2.inspector.blocks`, `nemesis.l3.honeypot.hits`, `nemesis.l4.oracle.risk_score`)
- テスト: `tests/test_nemesis_oracle.py`

> MS-B4+ (L5 Shield / L6 Compliance / Red Team) はインフラ整備後に着手。詳細は `Nemesis Full Install` ドキュメント参照。

---

### MS-C1 — CGRF コンプライアンス CLAUDE.md + 監査スクリプト ✅ 完了

- `CLAUDE.md` (リポジトリルート): SRS コード一覧・TaskIR 13ブロック規約・CGRF 4フィールド要件
- `tools/cgrf_audit.py`: 全 `.py` モジュールの CGRF 4フィールド存在確認 → JSON/Markdown レポート
- `.gitlab-ci.yml` / `.github/workflows/cgrf_audit.yml`: `cgrf-compliance-check` ジョブ追加
- CGRF Tier 0 / `_EXECUTION_ROLE = "TOOL"`
- テスト: `tests/test_cgrf_audit.py`

### MS-C2 — Notion SMP レジストリ DB ✅ 完了

- `src/infra/smp_notion_sync.py`: `sync_smp_registry()` — 全モジュールを Notion SMP DB に upsert
- `src/infra/notion_mca_client.py` 拡張: `create_smp_entry()` / `update_smp_entry()`
- 依存: `NOTION_TOKEN` + `NOTION_SMP_REGISTRY_DB_ID`
- dry_run=True デフォルト (認証情報未設定でも安全)
- テスト: `tests/test_smp_notion_sync.py`

### MS-C3 — VCCSakeReader + CAPS grade 統合 ✅ 完了

- `src/integrations/vcc/sake_reader.py`: `VCCSakeReader` — `.sake` ファイル読み込み・CAPS grade マッピング
- `src/contracts/diagnostics.py` 変更: `HealthCodeMetrics.caps_grade: str = "UNKNOWN"` フィールド追加
- CGRF Tier 1 / `_EXECUTION_ROLE = "INTEGRATION"`
- テスト: `tests/test_sake_reader.py`

---

## Risks & Mitigations (改訂版)

| リスク                            | 軽減策                                                          |
| ------------------------------ | ------------------------------------------------------------ |
| NATS 未接続 (ローカル開発)              | `NATS_URL` 未設定時はスタブモードで動作、NATS イベントはログのみ                     |
| CRP サイクル完了待ちタイムアウト             | `wait_for()` に `timeout` + `fallback=stub_result` を実装        |
| Perplexity 診断の無音劣化 (401/429)   | preflight チェック + `blockers` 列への明示 + dry_run デフォルト            |
| VCC ビルドフェーズと Citadel Lite の時間差 | Supabase `vcc_loop_state` でポーリングして非同期協調                      |
| OAD Reflex 修正と既存コードの衝突         | `should_trigger_reflex: bool` フラグで Citadel Lite 側から明示的に有効化する |
| OrchestratorV3 既存テストの破損        | `diagnostics_loop=None` デフォルト + `enabled=false` によるスキップ      |

---

## Perplexity Loop — ギャップ分析 (Gap G4 / G5)

Perplexity Control Loop v2 との統合で判明した未解消ギャップ。MS-A2 / MS-A3 にて対処する。

| ギャップ   | カテゴリ               | 内容                                                                                                                                       | 対応 MS                                        |
| ------ | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| **G4** | NATS イベント未整合       | `aegis.think.complete` / `aegis.codegen.complete` が Citadel Lite の購読リストに未追加。Perplexity Loop の思考完了・コード生成完了イベントを loop_orchestrator が受け取れない | MS-A2: `bridge_client.py` の subscribe リストに追加 |
| **G5** | Supabase 補助テーブル未作成 | `cycle_history` (Perplexity 診断サイクル履歴) + `alerts` (アラート一覧) テーブルが未定義。現状 `vcc_loop_state` に全て詰め込まれており、クエリ効率が低下                              | MS-A1: migration ファイルに追加                     |

> G4 の `aegis.*` Subject は Perplexity Loop が内部で使用する subject 名前空間。Citadel Lite は購読のみ（発行しない）。

---

## SMP (Software Module Profile) 統合

**評価日**: 2026-03-05
**評価結果**: citadel_lite_repo は SMP の TaskIR 13ブロック・CAPS Profile・AIMB を部分的に実装済み。`CITADEL_LLM/SAKE` 固有依存コンポーネントはスコープ外として分離する。

### SMP 4層 vs citadel_lite 対応

| SMP 層            | 内容                                         | citadel_lite 対応                                              | ステータス                                        |
| ---------------- | ------------------------------------------ | ------------------------------------------------------------ | -------------------------------------------- |
| **TaskIR**       | 13ブロック (purpose〜test_spec)                 | CGRF v3.0 の `_MODULE_NAME`/`_VERSION`/`_TIER`/`_ROLE` 4フィールド | ✅ CGRF v3.0 で対応済み                            |
| **CAPS Profile** | grade (T1〜T5)・trust_score・confidence・risk  | `CitadelHealthSnapshot.overall_grade` + AIS caps_profile     | ✅ MS-C3 完了 (VCCSakeReader + grade マッピング実装済み) |
| **AIMB**         | xp_values・tp_values・caps_rating・multiplier | AIS XP/TP 経済システム (AIS College)                               | ✅ AIS College 経由で対応済み                        |
| **F977 Lineage** | コード生成トレース・AIMB ヘッダー生成                      | CGRF `_MODULE_VERSION` のみ                                    | ❌ F977 は CITADEL_LLM 固有 → スコープ外              |

### 今すぐ実装可能 (MS-C1〜C3)

#### MS-C1 — CGRF コンプライアンス CLAUDE.md + 監査スクリプト

**目的**: 全開発者が CGRF 4フィールド要件と SRS コード体系を参照できる基盤を整備し、CI で自動監査する。

| 成果物                    | 内容                                                                                                         |
| ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| `CLAUDE.md` (リポジトリルート) | SRS コード一覧・TaskIR 13ブロック規約・CGRF 4フィールド要件・プロジェクト規約                                                           |
| `tools/cgrf_audit.py`  | 全 `.py` モジュールの `_MODULE_NAME`/`_MODULE_VERSION`/`_CGRF_TIER`/`_EXECUTION_ROLE` 存在確認 → JSON/Markdown レポート生成 |
| `.gitlab-ci.yml` 追加ジョブ | `cgrf-compliance-check` — `cgrf_audit.py` を実行し、strict mode では CI 失敗                                        |

```python
# tools/cgrf_audit.py
_MODULE_NAME    = "cgrf_audit"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 0       # Tier 0 (UTILITY)
_EXECUTION_ROLE = "TOOL"
```

#### MS-C2 — Notion SMP レジストリ DB

**目的**: citadel_lite 全モジュールの SMP メタデータを Notion DB に同期し、MCA / EVO Tracker と統合する。

| ファイル                                | 内容                                                                                                         |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `src/infra/smp_notion_sync.py`      | `sync_smp_registry(modules: List[dict], dry_run=True)` — citadel_lite 全モジュールを Notion SMP レジストリ DB に upsert |
| `src/infra/notion_mca_client.py` 拡張 | `create_smp_entry()` / `update_smp_entry()` ブロックビルダー追加                                                     |

**Notion SMP レジストリ DB スキーマ:**

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

#### MS-C3 — VCCSakeReader + CAPS grade 統合

**目的**: `.sake` プロファイルを Citadel Lite が消費できる Adapter を追加し、CAPS grade を `CitadelHealthSnapshot` に組み込む。

| ファイル                                  | 内容                                                  | `_EXECUTION_ROLE` |
| ------------------------------------- | --------------------------------------------------- | ----------------- |
| `src/integrations/vcc/sake_reader.py` | `VCCSakeReader` — `.sake` ファイル読み込み・CAPS grade マッピング | `INTEGRATION`     |

```python
# src/integrations/vcc/sake_reader.py
_MODULE_NAME    = "sake_reader"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"

class VCCSakeReader:
    """Adapter: .sake プロファイル → SakeFile / CAPS grade"""

    def load(self, path: str) -> "SakeFile":
        """JSON / YAML .sake ファイルを SakeFile dataclass に変換"""
        ...

    def to_health_grade(self, caps_profile: dict) -> str:
        """CAPS trust_score → T1〜T5 グレード変換"""
        score = caps_profile.get("trust_score", 0.0)
        if score >= 0.9:  return "T1"
        if score >= 0.75: return "T2"
        if score >= 0.6:  return "T3"
        if score >= 0.4:  return "T4"
        return "T5"
```

**`CitadelHealthSnapshot.code` フィールド追加:**

```python
@dataclass
class HealthCodeMetrics:
    pipeline_pass_rate: float = 0.0
    vcc_test_passed: int = 0
    vcc_test_failed: int = 0
    coverage_pct: float = 0.0
    caps_grade: str = "UNKNOWN"   # ← MS-C3 追加: T1〜T5 (VCCSakeReader 経由)
```

### スコープ外 (SMP 関連)

| コンポーネント                   | 理由                                               |
| ------------------------- | ------------------------------------------------ |
| **F941 SAKEBuilder 本体**   | `CITADEL_LLM/SAKE/` への強いパス依存・`.sake` 生成ロジック全体    |
| **F977 Lineage Tracker**  | AIMB ヘッダー生成フロー全体が `CITADEL_LLM/SAKE/` 専用         |
| **F991 Schema Generator** | TaskIR JSON → Pydantic 自動生成は `CITADEL_LLM` 専用ツール |
| **F999 テストハーネス**          | `.sake` ファイル消費テストは `CITADEL_LLM/SAKE/` パス依存      |

> F993 テスト (`test_f993_and_sake.py`, `test_f993_python_backend.py`, `test_f993_typescript_backend.py`) は citadel_lite B 固有として保持するが、CI 実行には `CITADEL_LLM/SAKE/` パス設定が必要。

---

## Out-of-Scope

- **Nemesis L5 Shield / L6 Compliance / Red Team (MS-B4+)**: インフラ整備 (Ansible / Helm / Terraform) が前提。MS-B1〜B3 完了後に判断する。
- `stagger_chain.py` 統合: MS-8 (CONFIDENCE_WRAPPER JSON 衝突問題解決後)
- PostHog / Stripe / Metabase の実 API 実装: stub のみ
- VCC 内部ビルドロジック: VCC 自体は外部システムとして扱い、adapter 経由で操作する
- **F941 / F977 / F991 / F999** (SMP 関連): `CITADEL_LLM/SAKE/` 固有依存のため citadel_lite_repo には組み込まない。VCCSakeReader (MS-C3) のみ adapter として切り出す

---

## 参照ドキュメント

| ファイル                                                                                                     | 内容                                                                                                     |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `docs/notion_exports/Finance Guild — VCC Build Instructions & Guardrails__487c244811.txt`                | VCC ガードレール・SRS コード・フェーズ定義                                                                              |
| `docs/notion_exports/Finance Guild — VCC Appendix G_...txt`                                              | CRP v2.0 ハードニング (FIX-001〜008)                                                                          |
| `docs/notion_exports/Finance Guild — VCC Appendix H_...txt`                                              | CRP v2.1 Perplexity Bridge (BRIDGE-001〜009)                                                            |
| `docs/notion_exports/Appendix H — Phase 2.1 CRP ↔ Perplexity Bridge Implementation Code__f3ffdf0fde.txt` | Bridge 実装コード (NATS publisher/subscriber)                                                               |
| `docs/notion_exports/Appendix I — Phase 2.5 OAD Integration Bridge Implementation Code__a55ab07e61.txt`  | OAD 統合実装コード (oad_nats.py パターン)                                                                         |
| `docs/notion_exports/VCC Health Check — VCC-FIN-20260228-2000__a989b5ba81.txt`                           | 最新ヘルスチェック結果                                                                                            |
| `ROADMAP_VCC_OAD_PERPLEXITY.md`                                                                          | 本ブループリントに基づく実装ロードマップ                                                                                   |
| `blueprints/CGRF-v3.0-Complete-Framework.md`                                                             | Tier 0〜3 定義・`_EXECUTION_ROLE` 要件・モジュールヘッダー標準                                                           |
| `blueprints/AGS-System-Spec-v1.0.md`                                                                     | Constitutional Council (S00〜S03)・CAPS グレード・guardian_logs スキーマ (Phase 24 統合済み)                          |
| `blueprints/REFLEX-System-Spec-v1.0.md`                                                                  | OAD Reflex Engine の元設計 (OBSERVE→DIAGNOSE→RESPOND→VERIFY→LEARN)・F924/F950/F960 パターン原型                   |
| `docs/notion_exports/Nemesis Full Install — VCC Pull Script + File Map__b115dc36a6.txt`                  | Nemesis L1〜L6 + Red Team 全ファイルマップ・インストールスクリプト・ENV テンプレート                                               |
| `docs/notion_exports/Nemesis Red Team — Autonomous Self-Scan Vulnerability Scanner__16393bf89a.txt`      | Red Team 8モジュール (RT-RECON/INJECT/AUTH/HONEY/EXFIL/ESCAPE/LLM/SUPPLY)・Supabase スキーマ・NATS ストリーム          |
| `docs/notion_exports/` (SMP 関連)                                                                          | Software Module Profile (SMP) 評価レポート — TaskIR 13ブロック・CAPS Profile・AIMB・F941/F977/F991/F993/F999 スコープ分析 |

---

*Note: VCC は抽象的なビルドコンポーネントではなく、Finance Guild の LLM 自律ビルダーとして定義された。*
*Citadel Lite 側は VCC をアダプター経由で操作し、CRP イベントと健全性スナップショットを消費する立場に立つ。*
