# Citadel Lite Evolution Blueprint v2

## Roadmap Translator + MCA 統合に向けた設計指針

生成日: 2026-02-19 (v2 — professors_bookmaker, MCA資産, CGRF準拠要件を統合)
更新日: 2026-02-22 (MS-3 Roadmap Tracker & API 完了を反映)
更新日: 2026-02-23 (MS-6 提案実行 + SANCTUM 完了、教授 JSON 出力統一を反映)
更新日: 2026-02-25 (MS-7 Notion/Supabase/可視化 完了を反映)
更新日: 2026-02-27 (MS-8 汎用拡張 + GGUF + CI 統合 完了を反映)
更新日: 2026-02-28 (Event JSON v1 契約修正 + datetime deprecation 一掃を反映)
対象リポジトリ: `citadel_lite_repo`

---

## 1. 今できていること（Current State）

### 1.1 コアパイプライン（Phase 0〜27 完了）

| カテゴリ                             | 実装状況                                           | 主要ファイル                                                                         |
| -------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------ |
| **エージェントパイプライン**                 | Sentinel→Sherlock→Fixer→Guardian の4段診断         | `src/agents/sentinel_v2.py`, `sherlock_v3.py`, `fixer_v3.py`, `guardian_v3.py` |
| **A2A プロトコル**                    | エージェント間ハンドオフ、状態蓄積                              | `src/a2a/protocol.py`, `agent_wrapper.py`                                      |
| **AGS 憲法パイプライン**                 | S00→S01→S02→S03 の4段階承認                         | `src/ags/pipeline.py`, `s00_generator.py`〜`s03_archivist.py`                   |
| **AIS XP/TP 経済**                 | デュアルトークン、CAPS グレード (D〜S)                       | `src/ais/engine.py`, `profile.py`, `costs.py`, `rewards.py`                    |
| **CGRF v3.0**                    | Tier 0〜3 ガバナンス、CLIバリデータ                        | `src/cgrf/cli.py`, `validator.py`, `README.md`                                 |
| **オーケストレータ V3**                  | メモリ注入、実行、REFLEX、テレメトリ                          | `src/orchestrator_v3.py`                                                       |
| **監視 (Phase 26 + MS-7)**         | Prometheus 16 メトリクス (+MCA 4本)、Grafana 2ダッシュボード | `src/monitoring/metrics.py`, `middleware.py`, `grafana/mca_dashboard.json`     |
| **VS Code Extension (Phase 27)** | リアルタイム CGRF Tier 検証                            | `vscode-extension/citadel-cgrf/`                                               |
| **実行レイヤー**                       | local/dry_run/github バックエンド                    | `src/execution/runner_V2.py`, `outcome_store.py`                               |
| **メモリ**                          | キーワード + FAISS ベクター検索                           | `src/memory/store_v2.py`, `vector_store.py`                                    |
| **監査**                           | SHA-256 ハッシュチェーン                               | `src/audit/logger.py`, `report.py`                                             |
| **LLM クライアント**                   | Azure OpenAI → OpenAI → Bedrock → fallback     | `src/llm/client.py`                                                            |
| **インテグレーション**                    | Notion, Supabase, Slack, Azure Services        | `src/integrations/`, `src/azure/`                                              |
| **MIKE**                         | 3エージェント再帰ソウルエンジン                               | `src/mike/engine/`                                                             |
| **Nemesis**                      | OWASP Top 10 ペンテスト                             | `src/nemesis/pentest_engine.py`                                                |
| **テスト**                          | 1133 テスト (2026-02-28 時点 — full suite passed)   | `tests/`                                                                       |

### 1.2 再利用可能な既存資産（外部リポジトリから取得済み）

#### professors_bookmaker → `src/mca/professors/` にコピー済み

| ファイル                           | サイズ         | MCA での用途                                                                                                                           |
| ------------------------------ | ----------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **`professor_base.py`**        | 73KB (v5.2) | **教授共通基盤** — LLM呼出し(OpenAI)、リトライ(3回)、出力パーシング、TF-IDFスコアリング、自己学習KB(FAISS 1536次元)、DossierWriter、Guardian連携。外部依存は全てtry/except+スタブで保護済み |
| **`prof_mirror.py`**           | 4KB         | **Mirror教授の直接ベース**                                                                                                                 |
| **`prof_oracle.py`**           | 2.6KB       | **Oracle教授の直接ベース**                                                                                                                 |
| **`prof_government.py`**       | 5.9KB       | **Government教授の直接ベース** — ENUM タグ付け、policy_notes、civic_impact                                                                       |
| **`prof_analyst.py`**          | 8.6KB       | **参考** — ENUM/Reflex抽出、key_findings、recommendations パターン                                                                           |
| **`prof_architect.py`**        | 12.9KB      | **参考** — 構造設計、Blueprint生成、tier logic パターン                                                                                          |
| **`prof_pattern_seeker.py`**   | 4KB         | **参考** — コードパターン検出（Mirror統合候補）                                                                                                     |
| **`prof_systems.py`**          | 18.5KB      | **参考** — システム思考、メトリクス分析                                                                                                            |
| **`prof_enum.py`**             | 7.8KB       | **参考** — 構造化JSON出力（提案モデルに応用可能）                                                                                                     |
| **`prof_enum_to_reflex.py`**   | 6.3KB       | **参考** — ENUM→アクションマッピング（proposals/executor に応用可能）                                                                                 |
| **`professor_template.py`**    | 4.4KB       | 新教授作成テンプレート                                                                                                                        |
| **`professor_config_role.py`** | 0.9KB       | 設定ヘルパー                                                                                                                             |

#### MCA ディレクトリ → `src/mca/` にコピー済み

| ファイル                                    | サイズ    | 用途                                                                                                                                                                                                                         |
| --------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`citadel_progression_assessment.py`** | 1,978行 | **MetricsAggregatorの直接ベース** — `Status`(enum+weight), `Priority`, `Deliverable`(id/name/status/phase/dependencies/blockers/completion_pct), `Phase`, `Component`(spec/code/tests/docs_complete), `CitadelProjectDefinition` |

#### MCA ディレクトリ（参照ドキュメント、コピー不要）

| ファイル                                        | 用途                                                                                               |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `MCA/reflex-ledger-caps-complete.md` (96KB) | **CAPS Handler + Ledger Handler + Reflex Handler** の完全Blueprint。Government教授のCAPS準拠チェックルール定義に使える |
| `MCA/EMERGENT_AI_METARULE.yaml` (44KB)      | **MCA-META-001（システム憲法）の原型**。SRSコード体系、ガバナンスルール、AI行動規範の詳細定義                                        |
| `MCA/COLLEGE_PROFESSOR_SYSTEM.md` (260KB)   | professors_bookmaker の上位設計思想                                                                     |

### 1.3 コード品質・安定性強化 (2026-02-21)

#### セキュリティ修正

| ファイル                                   | 修正内容                                       | 深刻度      |
| -------------------------------------- | ------------------------------------------ | -------- |
| `src/tools/vps_ssh.py`                 | `shlex.quote()` によるコマンドインジェクション防止          | CRITICAL |
| `src/reflex/dispatcher.py`             | `eval()` を `ast.literal_eval()` に置換        | CRITICAL |
| `src/mca/professors/professor_base.py` | `random.choice()` を `secrets.choice()` に置換 | MEDIUM   |

#### 安定性修正

| ファイル                                    | 修正内容                                                                                | 効果              |
| --------------------------------------- | ----------------------------------------------------------------------------------- | --------------- |
| `src/process_loop.py`                   | `max_runtime_seconds` パラメータ + `time.monotonic()` wall-clock timeout                 | ポーリングループの無限実行防止 |
| `src/streaming/emitter.py`              | `_MAX_HISTORY_PER_EVENT=500`, `_MAX_COMPLETED_EVENTS=100`, `max_idle_keepalives=20` | SSE メモリリーク防止    |
| `src/skills/registry.py`                | `List` → `deque(maxlen=10000)` 変換                                                   | 実行履歴の無制限成長防止    |
| `src/nemesis/runtime/nemesis_daemon.py` | `List` → `deque(maxlen=5000)` 変換                                                    | ジョブ履歴の無制限成長防止   |

#### Import 整理

| ファイル                           | 修正内容                                                                     |
| ------------------------------ | ------------------------------------------------------------------------ |
| `src/azure/foundry_agents.py`  | 存在しない v1 エージェント import を v2/v3 エイリアスに修正                                  |
| `src/a2a/agent_wrapper.py`     | 到達不能な v1 レガシーコード削除、`build_protocol()` を `build_protocol_v2()` のエイリアスに簡素化 |
| `src/agents/college_bridge.py` | 存在しない `src.college.service` への参照と `_try_college_service()` を削除           |
| `src/agents/council_bridge.py` | 存在しない `src.council.service` への参照と `_try_council_service()` を削除           |

### 1.4 教授 JSON 出力統一 (2026-02-23)

LLM が Markdown 形式で回答を返した際に構造化フィールドが空になる問題を恒久解消。全3教授の `_parse_output()` を JSON-first + Markdown フォールバック方式に統一。

| ファイル                                    | 変更内容                                                                                | 効果                                       |
| --------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------- |
| `src/mca/professors/prof_mirror.py`     | system_prompt を JSON-only 形式に変更、`_try_parse_json()` + `_normalize_json_result()` 追加 | LLM 出力形式に依存しない安定したパース                    |
| `src/mca/professors/prof_oracle.py`     | 同上 + `top_3_improvements` を `{title, description}` に正規化                             | health_status スコアが確実に数値で取得可能             |
| `src/mca/professors/prof_government.py` | 同上 + `approved`/`rejected`/`risk_assessment`/`conflict_arbitration` を完全正規化          | CAPS 承認/却下が空にならず、提案の executor スキップ問題を解消  |
| `src/infra/bedrock_professor_client.py` | モジュール冒頭に `load_dotenv()` 追加                                                         | エントリポイント依存なく `.env` から AWS クレデンシャルを確実に読込 |
| `tests/test_mca_professors.py`          | JSON 形式テスト 8件追加 (Mirror 3, Oracle 2, Government 3)                                  | JSON + Markdown 両形式を網羅 (28 tests total)  |

#### 3段 JSON フォールバック戦略

```
1. 直接 json.loads(text)                  → 成功すれば即採用
2. ```json ... ``` フェンスから抽出して json.loads() → 成功すれば採用
3. テキスト内の最初の { ... } ブロックを抽出して json.loads() → 成功すれば採用
→ 全て失敗した場合のみ従来の Markdown セクション regex 抽出にフォールバック
```

### 1.5 コード品質・安定性強化 (2026-02-28)

#### Event JSON v1 契約修正

commit `79f5497` + `87e2bab` で追加された A2A ハンドオフ契約のインターフェース不一致を修正。全 13 テストをグリーン化。

| ファイル                                       | 修正内容                                                                                                                                                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/contracts/handoff_packet.py`          | フィールド `id`/`source`/`destination` → `source_agent_id`/`target_agent_id`/`payload` に刷新。`validate()` をインスタンスメソッド化し jsonschema 検証に変更（構造検証のみ、空文字列は型有効）。`from_dict()` は jsonschema.ValidationError を送出 |
| `src/contracts/handoff_packet_contract.py` | フィールド `source`/`destination` → `id`/`timestamp`/`payload` (全て省略可能、None の場合は `ValueError("Missing required fields: [...]")` を `__post_init__` で送出)。`to_json()` メソッドを追加                             |
| `src/contracts/decision_contract.py`       | timestamp 検証を厳格化: `'T'` セパレータ必須 (`"2023-10-01 12:00:00"` 形式を拒否)                                                                                                                                   |
| `tests/contracts/test_handoff_packet.py`   | 旧インターフェース（ValueError 期待）から新インターフェース（jsonschema.ValidationError 期待 + 空文字列は有効）に更新                                                                                                                   |

#### datetime.utcnow() 一掃

Python 3.12 で deprecated となった `datetime.utcnow()` を全ファイルで `datetime.now(timezone.utc)` に置換。

| 対象ファイル                                                                         | 置換数                                                       |
| ------------------------------------------------------------------------------ | --------------------------------------------------------- |
| `src/agents/fixer_v3.py`, `guardian_v3.py`, `sherlock_v3.py`, `sentinel_v2.py` | 各2                                                        |
| `src/audit/report.py`, `src/approval/request.py`, `src/approval/response.py`   | 各1                                                        |
| `src/types.py`                                                                 | 2                                                         |
| `src/nemesis/pentest_engine.py`                                                | 5（うち1件は naive datetime 比較のため `.replace(tzinfo=None)` を付加） |
| `src/nemesis/runtime/nemesis_daemon.py`                                        | 多数                                                        |
| `src/nemesis/deploy/nemesis_cli.py`                                            | 1                                                         |
| `src/mike/engine/metadata_writer.py`                                           | 1                                                         |
| `tests/test_nemesis_runtime.py`                                                | 6                                                         |

置換後の deprecation warning: **0 件**。

### 1.6 アーキテクチャ上の強み

1. **ガバナンスの多層構造**: CGRF Tier → AGS 憲法裁判 → Guardian リスク評価
2. **経済的自律**: AIS の XP/TP がエージェントの行動範囲を制御
3. **改ざん耐性**: ハッシュチェーン監査により全決定が追跡可能（SANCTUM Publisher 含む）
4. **LLM フェイルオープン**: 4段階のバックエンドチェーンでグレースフル・デグラデーション
5. **REFLEX 自己修復**: observe→diagnose→respond→verify→learn の5段階ループ
6. **テストカバレッジ**: 1133 テスト — 全エージェント・教授・実行エンジンに unit + integration テスト完備
7. **教授基盤の再利用**: `ProfessorBase` v5.2 が LLM呼出し・スコアリング・自己学習を提供済み
8. **セキュリティ強化**: コマンドインジェクション防止、eval 排除、暗号学的ランダム使用
9. **安定性強化**: 全 unbounded データ構造に上限設定、wall-clock timeout 導入
10. **LLM 出力の堅牢化**: 全教授に JSON-first + Markdown フォールバック方式を適用、形式依存バグを恒久解消

---

## 2. 理想の姿に足りないもの（Gap Analysis）

### 2.1 Roadmap Translator レイヤー（認知層 — Perception）

**現状**: ✅ **MS-1, MS-2, MS-3 実装完了** (2026-02-22)。`src/roadmap_ir/` と `src/roadmap_translator/` と `src/roadmap/` が稼働中。

**実装済み（MS-1: Roadmap IR）**: 2026-02-20 完了

| コンポーネント                    | 目的                                                 | 状態            | テスト      |
| -------------------------- | -------------------------------------------------- | ------------- | -------- |
| `roadmap_ir/schema.json`   | JSON Schema Draft 2020-12                          | ✅ 実装済み        | —        |
| `roadmap_ir/types.py`      | Pydantic v2 モデル (7 enum, 16 model, Evidence union) | ✅ CGRF Tier 1 | 31 tests |
| `roadmap_ir/validators.py` | セマンティック検証 (ID重複, ソース参照, 依存先, 循環検出 等6チェック)          | ✅ CGRF Tier 1 | 31 tests |
| `roadmap_ir/__init__.py`   | パッケージ公開API                                         | ✅ CGRF Tier 1 | —        |

**実装済み（MS-2: Translator パイプライン）**: 2026-02-20 完了

| コンポーネント                                                    | 目的                                                    | 状態            | テスト            |
| ---------------------------------------------------------- | ----------------------------------------------------- | ------------- | -------------- |
| `roadmap_translator/translators/base.py`                   | `BaseTranslator` ABC + `TranslationPatch`             | ✅ CGRF Tier 1 | 8 tests        |
| `roadmap_translator/translators/readme.py`                 | README `**最新実装**` → items (§3.2)                      | ✅ CGRF Tier 1 | 8 tests        |
| `roadmap_translator/translators/markdown_roadmap.py`       | RoadMap `### Phase N:` → items (§3.3)                 | ✅ CGRF Tier 1 | 7 tests        |
| `roadmap_translator/translators/implementation_summary.py` | Impl Summary `### N. title ✅` → items (§3.4)          | ✅ CGRF Tier 1 | 8 tests        |
| `roadmap_translator/ingest.py`                             | ファイル読込 + SHA-256 fingerprint                          | ✅ CGRF Tier 1 | pipeline tests |
| `roadmap_translator/detect.py`                             | ファイル名+中身シグネチャ自動判定                                     | ✅ CGRF Tier 1 | pipeline tests |
| `roadmap_translator/normalize.py`                          | status/phase/gate/readiness/confidence 正規化 (§6)       | ✅ CGRF Tier 1 | pipeline tests |
| `roadmap_translator/merge.py`                              | item_id マージ + conflicts 生成 (§7)                       | ✅ CGRF Tier 1 | 8 tests        |
| `roadmap_translator/emit.py`                               | `roadmap_ir.json` + `roadmap_ir.report.md`            | ✅ CGRF Tier 1 | pipeline tests |
| `roadmap_translator/pipeline.py`                           | Ingest→Detect→Translate→Normalize→Merge→Validate→Emit | ✅ CGRF Tier 1 | 4 tests        |
| `roadmap_translator/cli.py`                                | `translate --in ... --out ... --report ...`           | ✅ CGRF Tier 1 | pipeline tests |
| `config/roadmap_translate.toml`                            | status 辞書, phase→revenue_gate map, readiness 表        | ✅             | —              |

**実装済み（MS-3: Roadmap Tracker & API）**: 2026-02-22 完了

| コンポーネント               | 目的                                                             | 状態            | テスト     |
| --------------------- | -------------------------------------------------------------- | ------------- | ------- |
| `roadmap/__init__.py` | モジュール初期化 + CGRF メタデータ                                          | ✅ CGRF Tier 1 | —       |
| `roadmap/models.py`   | `FinancePhase`, `RoadmapSnapshot` (既存 IR 型を再利用)                | ✅ CGRF Tier 1 | 2 tests |
| `roadmap/tracker.py`  | `RoadmapTracker`: IR 読み込み → snapshot + finance-guild 生成        | ✅ CGRF Tier 1 | 9 tests |
| `roadmap/api.py`      | FastAPI ルーター: `/roadmap/snapshot`, `/finance-guild`, `/health` | ✅ CGRF Tier 1 | 6 tests |
| `src/app.py` (修正)     | `roadmap_router` のマウント追加                                       | ✅             | —       |

**MS-8 実装済み（2026-02-27）**:

| コンポーネント                                              | 目的                                            | 状態            | テスト |
| ---------------------------------------------------- | --------------------------------------------- | ------------- | --- |
| `roadmap_translator/translators/generic_markdown.py` | 汎用 Markdown から items 抽出（allowlist 外は unknown） | ✅ CGRF Tier 1 | 25  |
| `roadmap_translator/translators/gitlog.py`           | git log から commit → phase マッピング               | ✅ CGRF Tier 1 | —   |
| `roadmap_translator/enricher.py`                     | GGUF/LLM による要約・リスクノート生成（抽出後のみ）                | ✅ CGRF Tier 1 | —   |

### 2.2 MCA Evolution レイヤー（行動層 — Action）

**現状**: ✅ **MS-4 完了** (2026-02-20) / **MS-6 完了** (2026-02-23)。`src/mca/` に MCA コアエンジン + 3教授 + 提案モデル + 実行エンジン + SANCTUM が稼働中。AWS Bedrock 経由で Claude Sonnet に接続確認済み (7 phases, 11 proposals, 0 errors — result.txt 2026-02-23)。

**実装済み（MS-4: MCA コアエンジン + 教授書換）**: 2026-02-20 完了

| コンポーネント                                  | 目的                                                               | 状態            | テスト      |
| ---------------------------------------- | ---------------------------------------------------------------- | ------------- | -------- |
| `mca/__init__.py`                        | モジュール初期化 + CGRF メタデータ                                            | ✅ CGRF Tier 1 | —        |
| `mca/evolution_engine.py`                | EvolutionEngine 7Phase オーケストレーション                                | ✅ CGRF Tier 1 | 18 tests |
| `mca/metrics_aggregator.py`              | MetricsAggregator (コード + プラン + Phase + IR メトリクス統合)               | ✅ CGRF Tier 1 | 18 tests |
| `mca/cli.py`                             | `evolve --meta ... --roadmap-ir ... --out ... --dry-run` CLI     | ✅ CGRF Tier 1 | 18 tests |
| `mca/professors/__init__.py`             | 教授パッケージ初期化                                                       | ✅ CGRF Tier 1 | —        |
| `mca/professors/bedrock_adapter.py`      | `BedrockProfessorBase`: Bedrock 対応 mixin ラッパー                    | ✅ CGRF Tier 1 | 21 tests |
| `mca/professors/prof_mirror.py` (書換)     | Mirror 教授: コードパターン + プランカバレッジ分析 — JSON-first + Markdown フォールバック  | ✅ CGRF Tier 1 | 28 tests |
| `mca/professors/prof_oracle.py` (書換)     | Oracle 教授: 戦略ガイダンス + 健全性評価 — JSON-first + Markdown フォールバック       | ✅ CGRF Tier 1 | 28 tests |
| `mca/professors/prof_government.py` (書換) | Government 教授: CAPS 準拠 + 提案承認/却下 — JSON-first + Markdown フォールバック | ✅ CGRF Tier 1 | 28 tests |
| `mca/proposals/__init__.py`              | 提案パッケージ初期化                                                       | ✅             | —        |
| `mca/proposals/models.py`                | `EvolutionProposal` + EP-CODE/EP-RAG/EP-SALES/EP-STALE/EP-GAP    | ✅ CGRF Tier 1 | 16 tests |
| `infra/__init__.py`                      | インフラパッケージ初期化                                                     | ✅             | —        |
| `infra/bedrock_professor_client.py`      | AWS Bedrock Claude 呼び出しクライアント                                    | ✅ CGRF Tier 1 | 21 tests |
| `config/mca_meta_001.yaml`               | MCA-META-001 システム憲法暫定版                                           | ✅             | —        |

**実装済み（MS-6 完了 — 2026-02-23）**:

| コンポーネント                     | 目的                                                  | 状態            | テスト |
| --------------------------- | --------------------------------------------------- | ------------- | --- |
| `mca/proposals/executor.py` | 承認済み提案の自動適用 (EP-CODE/RAG/SALES/STALE/GAP + dry_run) | ✅ CGRF Tier 1 | 15  |
| `mca/sanctum/publisher.py`  | SHA-256 ハッシュチェーン SANCTUM 記録 + dry_run 対応            | ✅ CGRF Tier 1 | 14  |

**実装済み（MS-7 完了 — 2026-02-25）**:

| コンポーネント                        | 目的                                                                                                                                                                                                                | 状態            | テスト |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | --- |
| `mca/__init__.py`              | MCA パッケージ初期化 (MS-7 新設)                                                                                                                                                                                            | ✅ CGRF Tier 1 | —   |
| `mca/notion_bridge.py`         | ブリッジ層 — `NotionRAGDocument`, `ZESPlanContext`, `SalesEvolutionMetrics` + `fetch_rag_documents()`, `build_zes_plan_context()`, `detect_coverage_gaps()`, `publish_evo_result()`, `create_coverage_gap_rag_pages()` | ✅ CGRF Tier 1 | 21  |
| `infra/notion_mca_client.py`   | Notion API (MCA 専用) — block builders + EVO Tracker ページ作成/パッチ + ZES RAG DB CRUD。`requests` ベース (既存 httpx `notion_client.py` と共存)                                                                                   | ✅ CGRF Tier 1 | 40  |
| `infra/supabase_mca_mirror.py` | Supabase REST ミラー — `automation_events` (既存) + `mca_proposals` (新規) テーブル。supabase-py 不要、REST 直呼び                                                                                                                  | ✅ CGRF Tier 1 | 14  |
| `monitoring/metrics.py` (修正)   | MCA Prometheus メトリクス 4本追加: proposals/approved Counter, health_score Gauge, cycle_duration Histogram                                                                                                               | —             | —   |
| `grafana/mca_dashboard.json`   | 9パネル MCA Evolution ダッシュボード                                                                                                                                                                                        | —             | —   |

**MS-8 実装済み（2026-02-27）**:

| コンポーネント                                              | 目的                           | 状態            | テスト |
| ---------------------------------------------------- | ---------------------------- | ------------- | --- |
| `roadmap_translator/translators/generic_markdown.py` | 汎用 Markdown → items 抽出       | ✅ CGRF Tier 1 | 25  |
| `roadmap_translator/translators/gitlog.py`           | git log → commit-phase マッピング | ✅ CGRF Tier 1 | —   |

### 2.3 統合レイヤー（Roadmap IR × MCA）

| コンポーネント                                   | 目的                                             | 優先度 |
| ----------------------------------------- | ---------------------------------------------- | --- |
| `integrations/roadmap_ir_ingestor.py`     | `ingest_roadmap_ir()` — IR の metrics を MCA に注入 | P0  |
| `integrations/roadmap_conflict_router.py` | IR の `conflicts[]` を Government 教授に渡す          | P1  |
| `integrations/roadmap_to_mca_mapper.py`   | `revenue_gate` ↔ `ZES_TIERS` マッピング             | P1  |
| 統合 CLI                                    | `translate → evolve → publish` 一括パイプライン        | P1  |

### 2.4 インフラ・外部接続

| コンポーネント                             | 目的                                      | 優先度 | 備考                                                                                                              |
| ----------------------------------- | --------------------------------------- | --- | --------------------------------------------------------------------------------------------------------------- |
| `infra/bedrock_professor_client.py` | AWS Bedrock 経由で Claude Sonnet を叩くクライアント | ✅   | **MS-4 実装完了** — `load_dotenv()` 追加済み (2026-02-23)、モデル ID は `AWS_BEDROCK_MODEL_ID` で切替可能                         |
| `infra/notion_mca_client.py`        | Notion ZES RAG DB への CRUD               | ✅   | **MS-7 実装完了** — block builders + EVO Tracker + ZES RAG DB CRUD。dry_run + 未設定時グレースフルスキップ対応                       |
| `infra/supabase_mca_mirror.py`      | Supabase へのメトリクス/正規 URL ミラー             | ✅   | **MS-7 実装完了** — `automation_events` + `mca_proposals` テーブル。REST 直呼び (supabase-py 不要)。dry_run + 未設定時グレースフルスキップ対応 |
| `infra/nexus_url_publisher.py`      | Citadel Nexus URL 生成                    | P2  | MS-8 対応予定                                                                                                       |

---

## 3. 開発するうえで重要なファイルと理由

### 3.1 修正が必要な既存ファイル

| ファイル                                        | 重要度     | 理由                                                                                                                  |
| ------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| **`src/app.py`**                            | **最重要** | FastAPI アプリのルーターマウントポイント。`/roadmap/*` と `/mca/*` を追加。全統合の入口                                                         |
| **`src/config.py`**                         | **最重要** | AWS Bedrock教授接続、GGUFモデルパス、Translator設定、MCA設定を追加                                                                     |
| **`src/mca/professors/professor_base.py`**  | **最重要** | Bedrock アダプター追加。現状 OpenAI のみの `refine_text_with_llm()` に Bedrock バックエンドを追加。または別ファイル `bedrock_adapter.py` で override |
| **`src/mca/professors/prof_mirror.py`**     | **重要**  | MCA 仕様の system_prompt + `_parse_specialized_llm_output()` に書換                                                       |
| **`src/mca/professors/prof_oracle.py`**     | **重要**  | 同上                                                                                                                  |
| **`src/mca/professors/prof_government.py`** | **重要**  | CAPS 準拠チェック + 提案承認/却下ロジックに書換                                                                                        |
| **`src/types.py`**                          | **重要**  | Roadmap IR 関連の型を追加するか別モジュールから参照する判断                                                                                 |
| **`citadel.config.yaml`**                   | **重要**  | `roadmap:`, `mca:`, `bedrock_professors:` セクション追加                                                                   |
| **`src/monitoring/metrics.py`**             | **参照**  | MCA 固有 Prometheus メトリクス 4本追加済み (MS-7 完了) — proposals/approved Counter, health_score Gauge, cycle_duration Histogram |
| **`src/audit/logger.py`**                   | **参照**  | SANCTUM 記録のベースライン                                                                                                   |

### 3.2 新規作成が必要なファイル（最重要のみ）

| ファイル                                          | 重要度     | 理由                                                  |
| --------------------------------------------- | ------- | --------------------------------------------------- |
| **`src/roadmap_ir/schema.json`**              | **最重要** | 全システムの契約。これが定まらないと何も実装できない                          |
| **`src/roadmap_ir/types.py`**                 | **最重要** | schema.json の Pydantic 実装                           |
| **`src/roadmap_translator/pipeline.py`**      | **最重要** | Translator パイプライン全フロー制御                             |
| **`src/mca/evolution_engine.py`**             | **最重要** | MCA のコアエンジン                                         |
| **`src/mca/professors/bedrock_adapter.py`**   | **最重要** | ProfessorBase と AWS Bedrock を接続する薄いレイヤー             |
| **`src/mca/metrics_aggregator.py`**           | **最重要** | `citadel_progression_assessment.py` を拡張してIRメトリクスを統合 |
| **`src/integrations/roadmap_ir_ingestor.py`** | **重要**  | Roadmap IR → MCA 接続。フィードバックループの心臓部                  |

### 3.3 参照すべき既存パターン

| パターン                  | 既存の実装場所                                       | 新規開発で活用する方法                                         |
| --------------------- | --------------------------------------------- | --------------------------------------------------- |
| CLI エントリポイント          | `cgrf.py`, `src/cgrf/cli.py`                  | `roadmap_translator/cli.py`, `mca/cli.py` の構造テンプレート |
| AGS 4段パイプライン          | `src/ags/pipeline.py`                         | MCA Evolution Cycle のステージ制御の参考                      |
| LLM フォールバックチェーン       | `src/llm/client.py`                           | Bedrock アダプターのエラーハンドリング                             |
| CGRF メタデータ付与          | `src/types.py` CGRFMetadata                   | 新モジュールの CGRF Tier 1 準拠（後述 §3.4）                     |
| 教授の process_thought() | `professor_base.py`                           | MCA 教授の `analyze()` メソッド設計                          |
| 教授の出力パーシング            | `prof_analyst.py` の `_extract_list_section()` | Mirror/Oracle の構造化出力抽出                              |
| 進捗評価データモデル            | `citadel_progression_assessment.py`           | MetricsAggregator のベースモデル                           |
| CAPS ルール              | `MCA/reflex-ledger-caps-complete.md`          | Government 教授の承認基準                                  |
| システム憲法                | `MCA/EMERGENT_AI_METARULE.yaml`               | MCA-META-001 の原型                                    |
| ハッシュチェーン監査            | `src/audit/logger.py`                         | SANCTUM 記録                                          |
| Prometheus メトリクス      | `src/monitoring/metrics.py`                   | MCA 固有メトリクスの追加                                      |

### 3.4 CGRF 準拠要件（全新規モジュール共通）

`src/cgrf/README.md` に定義された Tier 1 要件を全新規モジュールに適用する:

```python
# 全新規 .py ファイルに必須
_MODULE_NAME = "evolution_engine"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1  # 最低 Tier 1 (Development) 準拠

def _generate_cgrf_metadata(...) -> CGRFMetadata:
    ...
```

**Tier 1 チェックリスト**:

- モジュール docstring 必須
- `_MODULE_NAME`, `_MODULE_VERSION`, `_CGRF_TIER` 定数必須
- 対応テストファイル `tests/test_{module_name}.py` 必須
- `python cgrf.py validate --module <path> --tier 1` がパスすること

---

## 4. 現状では情報が足りずにできないもの

### 4.1 外部サービスの接続情報

| 不足情報                           | 影響範囲                   | 必要なアクション                                   |
| ------------------------------ | ---------------------- | ------------------------------------------ |
| **Notion ZES RAG Database ID** | `mca/notion_bridge.py` | ドキュメントに `4f323075-bac9-...` と記載あるが実環境確認が必要 |
| **Notion API トークン**            | 全 Notion 連携            | Notion Integration 作成 + トークン発行             |
| **Supabase プロジェクト URL + Key**  | メトリクスミラーリング            | Supabase ダッシュボードから取得                       |
| **Citadel Nexus URL / API 仕様** | 正規 URL 公開              | Nexus サーバーの情報                              |
| **GitLab リポジトリ URL + Push 権限** | SANCTUM Phase 7A       | デプロイキー or アクセストークン                         |

### 4.2 ビジネスロジックの未確定事項

| 不足情報                                 | 影響範囲                             | 対応策                                        |
| ------------------------------------ | -------------------------------- | ------------------------------------------ |
| **Phase 19〜27 の revenue_gate マッピング** | Translator の `PHASE_REVENUE_MAP` | **仮マッピング確定済み（下表参照）**。Kohei の正式承認後に差し替え     |
| **MCA-META-001 システム憲法**              | MCA Phase 2 のメタ文書                | `MCA/EMERGENT_AI_METARULE.yaml` を原型に暫定版を作成 |

#### Phase 19〜27 仮 revenue_gate マッピング

| Phase | 内容                                         | revenue_gate (仮) | 根拠                     |
| ----- | ------------------------------------------ | ---------------- | ---------------------- |
| 19    | Core Infrastructure (A2A, V3 基盤)           | `core`           | プラットフォーム基盤             |
| 20    | Core Infrastructure (Memory V2, Runner V2) | `core`           | プラットフォーム基盤             |
| 21    | CGRF Tier 1 Full Compliance                | `core`           | ガバナンス基盤                |
| 22    | Auto-Execution & Auto-Merge                | `core`           | 自動化基盤                  |
| 23    | Integration Tests (7ファイル41テスト)             | `core`           | 品質基盤                   |
| 24    | AGS Pipeline (憲法的司法4段階)                    | `core`           | ガバナンス基盤                |
| 25    | AIS XP/TP Economy (Dual-Token)             | `zes_agent`      | ZES Agent の課金・経済モデルに直結 |
| 26    | Monitoring & Observability (Prometheus)    | `core`           | 運用基盤                   |
| 27    | VS Code Extension (CGRF IDE 検証)            | `tradebuilder`   | 開発者ツーリング               |

> **注**: Phase 19-20 は個別に名前が付いていないが、Core Infrastructure (A2A, Orchestrator V3, LLM, Memory, Execution Runner, Audit) の構築フェーズに該当。
> | **ZES プラン機能一覧** | Oracle 教授の tier coverage 評価 | 仮データで開発 |
> | **CAPS プロトコルの教授版ルール** | Government 教授の承認基準 | `MCA/reflex-ledger-caps-complete.md` + `src/ags/caps_stub.py` を参考に定義 |
> | **Notion カテゴリ → ドメインマッピング** | カバレッジギャップ検出 | `mca_update_notion.txt` の記載を参考に初期マッピング |

### 4.3 技術的な未確定事項

| 不足情報                             | 選択肢                                                                   | 推奨                                       |
| -------------------------------- | --------------------------------------------------------------------- | ---------------------------------------- |
| **ProfessorBase の Bedrock 統合方法** | (A) `professor_base.py` を直接修正 (B) `bedrock_adapter.py` で override     | **(B) を推奨** — 元の OpenAI パスを壊さず、テスト容易性を維持 |
| **MCA 教授のモデル選択**                 | (A) 全教授 Claude Opus 4.5 (B) Mirror/Oracle を Sonnet、Government のみ Opus | コスト次第。初期は **(A)** で統一し、後から最適化            |
| **GGUF モデルの選定**                  | Phi-3.5-mini Q4_K_M (推奨) / Qwen2.5-7B / 任意                            | 環境変数で切替可能。初期は未選定で OK                     |

---

## 5. 現状のリポジトリ構造 vs 理想の構造

### 5.1 現状（v2 — コピー済み資産を含む）

```
src/
├── a2a/           ✅ 存在
├── agents/        ✅ 存在（19ファイル）
├── ags/           ✅ 存在（4段パイプライン）
├── ais/           ✅ 存在（XP/TP経済）
├── approval/      ✅ 存在
├── audit/         ✅ 存在
├── azure/         ✅ 存在
├── cgrf/          ✅ 存在（Tier 0-3 バリデータ）
├── dashboard/     ✅ 存在
├── execution/     ✅ 存在
├── github/        ✅ 存在
├── governance/    ✅ 存在
├── ingest/        ✅ 存在
├── integrations/  ✅ 存在
├── llm/           ✅ 存在
├── mcp_server/    ✅ 存在
├── memory/        ✅ 存在
├── mike/          ✅ 存在
├── monitoring/    ✅ 存在
├── nemesis/       ✅ 存在
├── notifications/ ✅ 存在
├── reflex/        ✅ 存在
├── skills/        ✅ 存在
├── streaming/     ✅ 存在
├── tools/         ✅ 存在
├── mca/                                    ✅ MS-4 完了 (2026-02-20) / MS-7 完了 (2026-02-25)
│   ├── __init__.py                         ✅ CGRF Tier 1 (MS-7 新設)
│   ├── cli.py                              ✅ evolve CLI
│   ├── evolution_engine.py                 ✅ 7Phase オーケストレーション
│   ├── metrics_aggregator.py               ✅ メトリクス統合集約
│   ├── notion_bridge.py                    ✅ MS-7 — ブリッジ層 (3 dataclass + 5 関数)
│   ├── citadel_progression_assessment.py   🟡 ベース資産（参考用）
│   ├── professors/                         ✅ 3教授 MCA 仕様書換完了
│   │   ├── __init__.py                     ✅ CGRF Tier 1
│   │   ├── professor_base.py               🟡 v5.2 (73KB, 変更なし)
│   │   ├── bedrock_adapter.py              ✅ BedrockProfessorBase mixin
│   │   ├── prof_mirror.py                  ✅ MCA 仕様書換済み
│   │   ├── prof_oracle.py                  ✅ MCA 仕様書換済み
│   │   ├── prof_government.py              ✅ MCA 仕様書換済み
│   │   ├── prof_analyst.py                 🟡 参考用
│   │   ├── prof_architect.py               🟡 参考用
│   │   ├── prof_pattern_seeker.py          🟡 参考用
│   │   ├── prof_systems.py                 🟡 参考用
│   │   ├── prof_enum.py                    🟡 参考用
│   │   ├── prof_enum_to_reflex.py          🟡 参考用
│   │   ├── professor_template.py           🟡 テンプレート
│   │   └── professor_config_role.py        🟡 設定
│   ├── proposals/                          ✅ 提案モデル + executor
│   │   ├── __init__.py
│   │   ├── models.py                       ✅ EP-CODE/RAG/SALES/STALE/GAP
│   │   └── executor.py                     ✅ MS-6 — 承認済み提案の自動適用
│   └── sanctum/                            ✅ MS-6 — SANCTUM ハッシュチェーン
│       ├── __init__.py
│       └── publisher.py                    ✅ SHA-256 チェーン + dry_run
├── roadmap_ir/    ✅ MS-1 完了 (2026-02-20) — schema.json, types.py, validators.py
├── roadmap_translator/ ✅ MS-2 完了 (2026-02-20) — 3 Translator + pipeline + CLI
│   └── translators/   ✅ readme.py, markdown_roadmap.py, implementation_summary.py
├── roadmap/       ✅ MS-3 完了 (2026-02-22) — models.py, tracker.py, api.py
└── infra/         ✅ MS-4 完了 (2026-02-20) / MS-7 完了 (2026-02-25)
    ├── __init__.py
    ├── bedrock_professor_client.py         ✅ AWS Bedrock Claude クライアント
    ├── notion_mca_client.py                ✅ MS-7 — Notion API (block builders + EVO Tracker + ZES RAG DB)
    └── supabase_mca_mirror.py              ✅ MS-7 — Supabase REST ミラー (automation_events + mca_proposals)
```

### 5.2 理想の追加構造

```
src/
├── roadmap_ir/                          # Roadmap IR スキーマ & 型
│   ├── __init__.py
│   ├── schema.json                      # JSON Schema (Draft 2020-12)
│   ├── types.py                         # Pydantic モデル
│   └── validators.py                    # セマンティック検証
│
├── roadmap_translator/                  # 決定的な Translator パイプライン
│   ├── __init__.py
│   ├── cli.py
│   ├── pipeline.py
│   ├── ingest.py
│   ├── detect.py
│   ├── normalize.py
│   ├── merge.py
│   ├── emit.py
│   ├── enricher.py                      # ✅ MS-8 実装済み
│   └── translators/
│       ├── base.py
│       ├── readme.py
│       ├── markdown_roadmap.py
│       ├── implementation_summary.py
│       ├── generic_markdown.py          # ✅ MS-8 実装済み
│       └── gitlog.py                    # ✅ MS-8 実装済み
│
├── roadmap/                             # GGUF エンジン & Tracker & API
│   ├── __init__.py
│   ├── models.py
│   ├── gguf_engine.py                   # ✅ MS-8 実装済み
│   ├── tracker.py
│   └── api.py
│
├── mca/                                 # MCA Evolution エンジン
│   ├── __init__.py
│   ├── cli.py
│   ├── evolution_engine.py              # 新規
│   ├── metrics_aggregator.py            # citadel_progression_assessment.py ベース
│   ├── notion_bridge.py                 # ✅ MS-7 実装済み
│   ├── citadel_progression_assessment.py # ベース資産（既存）
│   ├── professors/
│   │   ├── professor_base.py            # 既存（OpenAI）
│   │   ├── bedrock_adapter.py           # 新規（Bedrock 対応ラッパー）
│   │   ├── prof_mirror.py               # 既存→MCA仕様に書換
│   │   ├── prof_oracle.py               # 既存→MCA仕様に書換
│   │   ├── prof_government.py           # 既存→MCA仕様に書換
│   │   └── (参考用ファイル群)
│   ├── proposals/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── executor.py                  # ✅ MS-6 実装済み
│   └── sanctum/
│       ├── __init__.py
│       └── publisher.py                 # ✅ MS-6 実装済み
│
├── integrations/                        # 既存 + 追加
│   ├── roadmap_ir_ingestor.py
│   ├── roadmap_conflict_router.py       # (P1)
│   └── roadmap_to_mca_mapper.py         # (P1)
│
└── infra/                               # 新規
    ├── __init__.py
    ├── bedrock_professor_client.py
    ├── notion_mca_client.py             # ✅ MS-7 実装済み
    ├── supabase_mca_mirror.py           # ✅ MS-7 実装済み
    └── nexus_url_publisher.py           # (P2 — MS-8)
```

---

## 6. 技術的判断のまとめ

### 6.1 確定事項

- Translator は **決定的** (regex + ルールベース)。LLM を抽出に使わない
- MCA 教授は **AWS Bedrock** 経由で Claude Opus 4.5 を使用（`BedrockProfessorBase` mixin で Bedrock adapter を追加）— **E2E 動作確認済み** (2026-02-20, 7 phases, 7 proposals, 0 errors)
- Roadmap IR は **JSON Schema Draft 2020-12** で厳密に定義
- 全決定は **SANCTUM** にハッシュチェーンで記録
- `conflicts[]` は揉み消さず Government 教授に渡して裁定
- Evidence は必ず **source_id + loc (行番号)** で追跡可能
- 新規モジュールは全て **CGRF Tier 1** 準拠（docstring + metadata + test）

### 6.2 設計判断（推奨）

- `src/roadmap_ir/` + `src/roadmap_translator/` + `src/mca/` の **3モジュール分離**
- `ProfessorBase` は **直接修正せず**、`bedrock_adapter.py` で Bedrock 対応を override — ✅ 実装済み
- `citadel_progression_assessment.py` をベースに `metrics_aggregator.py` を構築
- `MCA/EMERGENT_AI_METARULE.yaml` をベースに MCA-META-001 暫定版を作成
- `MCA/reflex-ledger-caps-complete.md` をベースに Government 教授の CAPS ルールを定義
- 設定は **`config/roadmap_translate.toml`** を新設し、status 辞書や regex を外出し
- テスト戦略は **Golden Test** (スナップショット比較) を中心に据える

---

*Generated: 2026-02-19 v2 — Updated: 2026-02-28 (Event JSON v1 契約修正 + datetime deprecation 一掃 — 1133 tests passed) — Citadel Lite Evolution Blueprint*
