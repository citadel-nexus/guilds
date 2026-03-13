# CITADEL NEXUS LITE — MVP (Minimum Viable Product) Implementation Checklist (Final Version → Translation into MVP) FOR Dmitry

## Complete Memory Layer + Multi-Agent Orchestration System

**Date:** January 27, 2026  
**Target:** Microsoft AI Dev Days Hackathon (Agentic DevOps Category)  
**Owner:** Kousaki (Memory Layer Lead)  
**Purpose:** Sharing the minimum viable product (MVP) configuration for the upcoming Microsoft AI Dev Days Hackathon

---

# MVP（ローカル最小通し）実装チェックリスト（完成形→MVPへの落とし込み）

## 0. 先に固定する前提（v0図に対応）

- v0図（概念／Azure配線／Sequence）を “正” として固定済み（君が宣言済み）

- MVPは **ローカル単体でE2Eが通る**ことを最優先

- Azure/Foundry/Copilotは **差し替え可能な“後段の配線”**として扱う
  
  citadel-technical-blueprint-kou…

---

# Phase 1：E2Eを通す「契約（インターフェース）」を固定

ここが一番重要。完成形の厚みを捨てても、**契約だけは固定**する。

## 1. Event契約を固定（Event JSON v1）

**固定（MVPでも本実装）**

- `types.EventJsonV1`（必須フィールドを決め打ち）
  
  - `schema_version="event_json_v1"`
  
  - `event_id`, `event_type`
  
  - `source`（github/ci/alert など）
  
  - `occurred_at`
  
  - `repo`, `ref/branch`（最低1つ）
  
  - `summary`
  
  - `artifacts`（log_excerpt / links を内包）  
    → 入力の唯一の真実として固定。
    
    citadel-technical-blueprint-kou…

**スタブ**

- Event Ingest（Functions/Webhook相当）はMVPでは不要  
  → `demo/events/*.json` を読み込むだけでOK
  
  citadel-technical-blueprint-kou…

## 2. Handoff Packet契約を固定（A2A引き継ぎの共通構造）

**固定**

- `types.HandoffPacket`
  
  - `event`（EventJsonV1）
  
  - `artifacts`
  
  - `memory_hits`（後で拡張）
  
  - `agent_outputs`（sentinel/sherlock/fixer/guardian の出力）
  
  - `risk`（risk_score等）
  
  - `audit_span_id`  
    → 「追記されて次に渡る」形式を固定。
    
    citadel-technical-blueprint-kou…

## 3. Decision契約を固定（Guardianの出力）

**固定**

- `types.Decision`
  
  - `action`: `approve | need_approval | block`
  
  - `risk_score`（0–100でも0–1でもOK）
  
  - `rationale`（短文）
  
  - `policy_refs`（配列：最初は空でもOK）
    
    citadel-technical-blueprint-kou…

---

# Phase 2：Orchestrator骨格（通しの背骨）を本実装

## 4. Orchestratorを作る（順番固定）

**固定（本実装）**

- `orchestrator.py`
  
  - outboxから1件取得（MVPはファイル入力でOK）
  
  - `audit.start()` を必ず呼ぶ
  
  - Sentinel → Sherlock → Fixer → Guardian の順に `handoff(packet)`
  
  - Guardian Decisionに応じて分岐
  
  - `audit.finish()` を必ず呼ぶ
    
    citadel-technical-blueprint-kou…

**スタブ**

- キュー（Service Bus / Outbox）は “ファイルOutbox” で代替
  
  - `demo/events/*.json` → そのまま “outbox扱い”
  
  - もしくは `outbox/pending/*.json` を読むだけ
    
    citadel-technical-blueprint-kou…

---

# Phase 3：4エージェントは「最小ロジック＋固定出力」でOK

完成形ではFoundry Agent Serviceに載る想定だけど、MVPは **同じI/Fでローカル関数**にする。

## 5. Sentinel（検知・分類）

**固定**

- `agents/sentinel.py`  
  入力：HandoffPacket → 出力：classification/severity/signals を `agent_outputs.sentinel` に追記

**スタブでOK**

- classificationはルールベースで十分（event_typeで分岐）
  
  citadel-technical-blueprint-kou…

## 6. Sherlock（診断）

**固定**

- `agents/sherlock.py`  
  出力：hypotheses/confidence/evidence を追記

**スタブでOK**

- 最初は `log_excerpt` 内のキーワード一致で仮説を作る  
  （例：`ModuleNotFoundError`, `ENV`, `PermissionDenied`）
  
  citadel-technical-blueprint-kou…

## 7. Fixer（修復提案）

**固定**

- `agents/fixer.py`
  
  - 出力：`fix_plan`（提案内容）＋`patch/pr_draft`（テキスト）＋`risk_estimate`

**スタブでOK**

- まずは “修正方針テキスト” を返すだけでOK（パッチ不要）

- `FIXER_MODE` を実装して **local/coping** 切替の口だけ作る
  
  - `local`: 文章生成
  
  - `copilot`: 後で実装（MVPではNotImplementedでもOK）
    
    citadel-technical-blueprint-kou…

## 8. Guardian（ガバナンス）

**固定（MVPでも“本体”扱い）**

- `agents/guardian.py`（もしくは `governance/engine.py`）
  
  - `risk_score` を計算
  
  - `Decision(action, rationale, policy_refs)` を返す

**スタブでOK**

- policyは最小3ルールで十分
  
  - `risk_score < 30` → approve
  
  - `30–70` → need_approval
  
  - `>=70` → block

- policy_refs は `"POLICY_DEMO_RISK_BAND_01"` など固定文字列でOK
  
  citadel-technical-blueprint-kou…

---

# Phase 4：Memory / Audit / Execution は「I/F固定 + 中身スタブ」

完成形ドキュメントはここが厚い。MVPは **差し替え前提でI/Fだけ固める**。

## 9. Memory Layer（最初は“固定事例3件”で良い）

**固定**

- `memory/store.py` に `recall(query, k) -> list[MemoryHit]` を用意

- `MemoryHit` 型（id, title, snippet, tags, confidence, link）

**スタブ**

- `memory/mock_corpus.json` を3件用意して返すだけ
  
  citadel-technical-blueprint-kou…

## 10. Audit / Logs（MVPでちゃんと残す）

**固定（本実装）**

- `audit/logger.py`
  
  - `audit.start(span_id, event_id)`
  
  - `audit.log(stage, payload)`
  
  - `audit.finish(outcome)`

- `audit/report.py`
  
  - `audit_report.json` を生成（event/decision/agent_outputs/links）

**スタブでOK**

- テレメトリ（App Insights等）は後で。まずは `out/audit/...` にJSON保存
  
  citadel-technical-blueprint-kou…

## 11. Execution（最初は“実行せず指示書を書く”）

**固定**

- `execution/runner.py` に `execute(decision, fix_plan) -> outcome` を用意

**スタブ**

- 実際のPR作成/CI rerunはしない  
  → `out/execution/<event_id>/action.json` を吐くだけでOK
  
  citadel-technical-blueprint-kou…

---

# Phase 5：MVPの“通し”合格条件（ここまでで一旦完成）

- コマンド一発で動く  
  `python -m src.orchestrator demo/events/ci_failed.sample.json`

- `out/audit/<event_id>/audit_report.json` が生成される

- `handoff_packet.json` に4エージェント出力が揃う

- Decisionが `approve|need_approval|block` のいずれかになる

- approve/need_approval の場合 `out/execution/.../action.json` が生成される
  
  citadel-technical-blueprint-kou…

---

# Phase 6：完成形へ近づける「差し替えポイント」（後段でDmitry連携）

MVPが通った後に、完成形ドキュメントへ寄せる順番。

## 12. Outbox → Service Busに差し替え（I/Fは維持）

- `outbox_adapter.py` を作り、sourceを file→servicebus に切替

## 13. Agents → Foundry Agent Serviceにラップ

- `agents/*.py` はI/F維持、内部呼び出しをFoundryに差し替え

## 14. Audit → App Insights / Storageへ

- `audit/logger` のbackendだけ差し替え

## 15. FixerCopilotを実装（必要なら）

- `FIXER_MODE=copilot` の中身を実装
  
  - PR作成/変更/テスト追加のどれか一つで十分

---

# 迷った時のルール（超重要）

- **固定するのは「契約（types）」と「Orchestratorの順番」と「Guardian decision」**

- **スタブにするのは「外部配線（Azure/Foundry/Copilot）」と「重いストア群」**

- **監査だけはMVPでも本物**（ここがCitadelらしさ）
  
  citadel-technical-blueprint-kou…
