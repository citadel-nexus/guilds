# Citadel Lite Evolution Roadmap v2

## Roadmap Translator + MCA 統合 — 開発マイルストン

生成日: 2026-02-19 (v2 — professors_bookmaker, MCA資産, CGRF準拠要件を統合)
更新日: 2026-02-22 (MS-3 Roadmap Tracker & API 完了を反映)
更新日: 2026-02-16 (MS-5 Roadmap IR × MCA 統合 完了を反映)
更新日: 2026-02-23 (MS-6 提案実行 + SANCTUM 完了、教授 JSON 出力統一を反映)
更新日: 2026-02-25 (MS-7 Notion/Supabase/可視化 完了を反映)
更新日: 2026-02-27 (MS-8 汎用拡張 + GGUF + CI 統合 完了を反映)
更新日: 2026-02-28 (Event JSON v1 契約修正 + datetime deprecation 一掃を反映)
前提: `EVOLUTION_BLUEPRINT_20260226.md` v2 と同時に参照すること

---

## マイルストン全体像

```
MS-1: Roadmap IR スキーマ & 型定義      ✅ 完了 (2026-02-20)
  ↓
MS-2: Translator 3本 + パイプライン     ✅ 完了 (2026-02-20)
  ↓
MS-3: Roadmap Tracker & API            ✅ 完了 (2026-02-22)
  ↓
MS-4: MCA コアエンジン + 教授書換        ✅ 完了 (2026-02-20)
  ↓
コード品質強化 (Security/Stability/Import) ✅ 完了 (2026-02-21)
  ↓
MS-5: Roadmap IR × MCA 統合            ✅ 完了 (2026-02-16) — 868 passed, 1 failed (pre-existing)
  ↓
MS-6: 提案実行 + SANCTUM               ✅ 完了 (2026-02-23) — 54 passed
  ↓
教授 JSON 出力統一                       ✅ 完了 (2026-02-23) — 28 passed (test_mca_professors)
  ↓
MS-7: Notion/Supabase/可視化           ✅ 完了 (2026-02-25) — 75 passed
  ↓
MS-8: 汎用拡張 + GGUF + CI 統合         ✅ 完了 (2026-02-27) — 49 passed
  ↓
コード品質強化 (Event JSON v1 + datetime) ✅ 完了 (2026-02-28) — 1133 passed (full suite)
```

### v1 → v2 の主な変更点

| 変更点                 | v1                         | v2                                                                                                |
| ------------------- | -------------------------- | ------------------------------------------------------------------------------------------------- |
| MS-4 の教授基盤          | ゼロから `base.py` を構築         | `professor_base.py` v5.2 (73KB) がコピー済み。`bedrock_adapter.py` を追加するのみ                               |
| MS-4 のメトリクス集約       | ゼロから構築                     | `citadel_progression_assessment.py` をベースに拡張                                                       |
| MS-4 の3教授           | ゼロから構築                     | `prof_mirror.py`, `prof_oracle.py`, `prof_government.py` がコピー済み。system_prompt + 出力パーサーを MCA 仕様に書換 |
| MS-4 の MCA-META-001 | 暫定テンプレートを作成                | `MCA/EMERGENT_AI_METARULE.yaml` (44KB) を原型として利用                                                   |
| MS-4 の CAPS ルール     | `src/ags/caps_stub.py` を参考 | `MCA/reflex-ledger-caps-complete.md` (96KB) を正式なルールソースに                                           |
| 全 MS の品質基準          | 未定義                        | **CGRF Tier 1 準拠**を全新規モジュールに義務化                                                                   |

---

## 全マイルストン共通: CGRF Tier 1 準拠要件

v2 では全新規 `.py` ファイルに以下を義務化する（`src/cgrf/README.md` 参照）:

```python
"""モジュール docstring（必須）"""
_MODULE_NAME = "module_name"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER = 1  # 最低 Tier 1 (Development) 準拠
```

**各マイルストンの完了基準に追加**:

- 全新規モジュールが `python cgrf.py validate --module <path> --tier 1` をパス
- 対応テストファイル `tests/test_{module_name}.py` が存在

---

## MS-1: Roadmap IR スキーマ & 型定義 ✅ 完了

**目的**: 全システムの共通契約（JSON Schema + Python 型）を確立する。これが定まらないと Translator も MCA も実装できない。

**完了日**: 2026-02-20
**実績**: 31 tests passed, CGRF Tier 1 全モジュール COMPLIANT

### 成果物

| ファイル                              | 内容                                                                                                                      | CGRF   |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ------ |
| `src/roadmap_ir/__init__.py`      | モジュール初期化 + CGRF メタデータ                                                                                                   | Tier 1 |
| `src/roadmap_ir/schema.json`      | JSON Schema Draft 2020-12 (Blueprint v1.1 の 2.5 節をそのまま採用)                                                               | —      |
| `src/roadmap_ir/types.py`         | Pydantic v2 モデル: `Source`, `Catalog`, `Item`, `Evidence` (FileLoc/Git/Text), `Conflict`, `Note`, `Metrics`, `RoadmapIR` | Tier 1 |
| `src/roadmap_ir/validators.py`    | セマンティック検証: item_id 重複禁止、evidence 無し item は status=unknown 強制、phase 番号と item_id の整合性                                     | Tier 1 |
| `tests/test_roadmap_ir_schema.py` | スキーマバリデーション + 型テスト                                                                                                      | —      |

### タスク

1. Blueprint v1.1 の JSON Schema (2.5節) を `schema.json` として配置
2. Pydantic モデルを `types.py` に実装（`Item`, `Evidence`, `Conflict`, `Note`, `Source`, `Catalog`, `Metrics`, `RoadmapIR`）
3. `validators.py` にセマンティックチェックを実装
   - `item_id` のユニーク制約
   - `status != "unknown"` なのに `evidence` が空の場合はエラー
   - `phase` があるのに `item_id` が `phase-xxx` でない場合は warning
   - `dependencies[]` の循環検出（オプション）
4. テスト: 正常系 + 異常系 (重複ID, evidence無しdone, enum外の値)
5. **CGRF メタデータ付与**: 各 `.py` に `_MODULE_NAME`, `_MODULE_VERSION`, `_CGRF_TIER` を追加
6. `.gitignore` に `models/*.gguf`, `.nexus/sanctum/` を追加

### 完了基準

- `schema.json` が jsonschema ライブラリで検証可能
- Pydantic モデルで `RoadmapIR` をシリアライズ/デシリアライズ可能
- セマンティック検証が全エラーパターンを捕捉
- テスト全パス
- `python cgrf.py validate --module src/roadmap_ir/types.py --tier 1` パス
- `python cgrf.py validate --module src/roadmap_ir/validators.py --tier 1` パス

### 不足情報

- なし（Blueprint v1.1 に JSON Schema の完全な定義あり）

---

## MS-2: Translator 3本 + パイプライン ✅ 完了

**目的**: README / RoadMap / Implementation Summary の3ドキュメントを決定的に Roadmap IR JSON に変換するパイプラインを構築する。

**完了日**: 2026-02-20
**実績**: 37 tests passed (readme 8, roadmap 7, impl_summary 8, merge 8, pipeline 4, determinism 2), 全12モジュール CGRF Tier 1 COMPLIANT

### 成果物

| ファイル                                                           | 内容                                                                            | CGRF   |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------ |
| `src/roadmap_translator/__init__.py`                           | モジュール初期化                                                                      | Tier 1 |
| `src/roadmap_translator/translators/base.py`                   | `BaseTranslator` 抽象クラス                                                        | Tier 1 |
| `src/roadmap_translator/translators/readme.py`                 | README Translator: `**最新実装**` ブロック → items 抽出                                 | Tier 1 |
| `src/roadmap_translator/translators/markdown_roadmap.py`       | RoadMap Translator: `### ✅ Phase N:` → items 抽出                               | Tier 1 |
| `src/roadmap_translator/translators/implementation_summary.py` | Impl Summary Translator: `### 1. ... ✅` → items 抽出                            | Tier 1 |
| `src/roadmap_translator/ingest.py`                             | ファイル読み込み + SHA-256 fingerprint 生成                                             | Tier 1 |
| `src/roadmap_translator/detect.py`                             | 入力タイプ判定（ファイル名ヒント + 中身シグネチャ）                                                   | Tier 1 |
| `src/roadmap_translator/normalize.py`                          | status/phase/gate/verify_status の正規化辞書                                        | Tier 1 |
| `src/roadmap_translator/merge.py`                              | item_id 単位のマージ + conflicts 生成                                                 | Tier 1 |
| `src/roadmap_translator/emit.py`                               | `roadmap_ir.json` + `roadmap_ir.report.md` 出力                                 | Tier 1 |
| `src/roadmap_translator/pipeline.py`                           | Ingest→Detect→Translate→Normalize→Merge→Validate→Emit                         | Tier 1 |
| `src/roadmap_translator/cli.py`                                | CLI: `translate --in ... --out roadmap_ir.json --report roadmap_ir.report.md` | Tier 1 |
| `config/roadmap_translate.toml`                                | status 辞書、phase regex 一覧、revenue gate マップ                                     | —      |
| `tests/test_translator_readme.py`                              | README Translator 単体テスト                                                       | —      |
| `tests/test_translator_roadmap.py`                             | RoadMap Translator 単体テスト                                                      | —      |
| `tests/test_translator_impl_summary.py`                        | Impl Summary Translator 単体テスト                                                 | —      |
| `tests/test_translator_merge.py`                               | マージ + conflicts テスト                                                           | —      |
| `tests/test_translator_pipeline.py`                            | Golden test（3ファイル → IR スナップショット比較）                                            | —      |
| `tests/test_translator_determinism.py`                         | 決定性テスト（同一入力 → 同一出力）                                                           | —      |

### タスク

1. `base.py`: `BaseTranslator` ABC を定義。`translate(lines: List[str], source_id: str) -> TranslationPatch`
2. `ingest.py`: ファイル読み込み、行分割、SHA-256 fingerprint、`Source` オブジェクト生成
3. `detect.py`: ファイル名パターンと中身シグネチャで Translator を自動選択
4. 3本の Translator を Blueprint v1.1 の §3.2〜3.4 の regex ルールに従って実装:
   - **README**: `**最新実装 (YYYY-MM-DD)**:` ブロック → 箇条書き → items
   - **RoadMap**: `### ✅ Phase N: title (完了)` → Phase items + ブロック内の根拠行
   - **Impl Summary**: `### 1. title ✅` → feature items + `#### 変更ファイル` → evidence
5. `normalize.py`: Blueprint v1.1 §6 の正規化ルールを辞書として実装
6. `merge.py`: Blueprint v1.1 §7 のマージルール + conflicts 生成
7. `emit.py`: JSON 出力 + Markdown レポート生成
8. `pipeline.py`: 全ステップのオーケストレーション
9. `cli.py`: argparse ベースの CLI（`src/cgrf/cli.py` のパターンを参考）
10. `roadmap_translate.toml`: 外出しの設定ファイル
11. テスト6本を実装
12. **CGRF メタデータ付与**: 全 `.py` に CGRF Tier 1 メタデータを追加

### 完了基準

- 3本の Translator が既存の README.md / RoadMap / Impl Summary を正しく抽出
- `roadmap_ir.json` が MS-1 の schema.json を通過
- conflicts が正しく生成される（同一 phase で status が矛盾する場合）
- Golden test が通過（入力固定 → 出力固定）
- 決定性テスト: 同一入力を2回走らせて diff がゼロ
- `python cgrf.py tier-check src/roadmap_translator/*.py --tier 1` が全パス

### 不足情報

- ~~**Phase 19〜27 の revenue_gate マッピング**~~: ✅ `config/roadmap_translate.toml` に仮マッピングとして実装済み
- ~~**既存ドキュメントの最新版のフォーマット確認**~~: ✅ 実データの見出しパターンを確認し、Blueprint v1.1 の regex と合致することを検証済み。テストで動作確認完了

---

## MS-3: Roadmap Tracker & API ✅ 完了

**目的**: Roadmap IR を読み込んでスナップショットを生成し、FastAPI エンドポイント経由で提供する。

**完了日**: 2026-02-22
**実績**: 17 tests passed (Tracker 9, Models 2, API 6), 全3モジュール CGRF Tier 1, 既存 IR 型を最大限再利用 (重複モデル 0)

> **実装方針**: `roadmap_ir.types` の `StatusEnum`, `RevenueGateEnum`, `Item`, `PhaseCompletion` 等を直接再利用。新規モデルは `RoadmapSnapshot` と `FinancePhase` のみ作成。

### 成果物

| ファイル                            | 内容                                                                             | CGRF   |
| ------------------------------- | ------------------------------------------------------------------------------ | ------ |
| `src/roadmap/__init__.py`       | モジュール初期化                                                                       | Tier 1 |
| `src/roadmap/models.py`         | `FinancePhase`, `RoadmapSnapshot` (既存 IR 型を import して再利用)                      | Tier 1 |
| `src/roadmap/tracker.py`        | `RoadmapTracker`: IR 読み込み → スナップショット生成、Finance Guild レポート                      | Tier 1 |
| `src/roadmap/api.py`            | FastAPI ルーター: `/roadmap/snapshot`, `/roadmap/finance-guild`, `/roadmap/health` | Tier 1 |
| `src/app.py` (修正)               | `roadmap_router` のマウント追加                                                       | —      |
| `tests/test_roadmap_tracker.py` | Tracker + Models + API 統合テスト (17 tests)                                        | —      |

### セキュリティ・安定性対策

| 対策                      | 内容                                                        |
| ----------------------- | --------------------------------------------------------- |
| ファイルサイズ上限               | `_MAX_IR_FILE_BYTES = 50MB` で巨大ファイル読み込みを防止                |
| パス正規化                   | `Path.resolve()` で path traversal を防止                     |
| datetime deprecation 回避 | `datetime.now(timezone.utc)` を使用 (`utcnow()` 不使用)         |
| IR 不在時のグレースフルデグラデーション   | lazy 初期化 + `/roadmap/health` は 503 ではなく `unavailable` を返す |

### 完了基準 (全達成)

- ✅ `/roadmap/snapshot` が MS-2 で生成した `roadmap_ir.json` を読んで正しいスナップショットを返す
- ✅ `/roadmap/finance-guild` が revenue_gate 別の完了率を返す
- ✅ 既存テストが全パス（regression なし）
- ✅ 全モジュール CGRF Tier 1 メタデータ付与済み

### 残課題

- **Revenue readiness の計算ロジック**: 暫定ロジック (`done / total`) で実装済み。MS-5 で MCA 教授に委譲可能。

---

## MS-4: MCA コアエンジン + 教授書換 ✅ 完了

**目的**: MCA Evolution Cycle のコアエンジンを構築し、コピー済みの教授ファイルを MCA 仕様に書き換え、AWS Bedrock 経由で動作させる。

**完了日**: 2026-02-20
**実績**: 55 tests passed (proposals 16, professors 21, engine+aggregator+cli 18), 全9モジュール CGRF Tier 1 COMPLIANT, E2E 動作確認済み (7 phases, 7 proposals, 0 errors)

> **v2 での変更**: 教授の「ゼロから構築」→「コピー済みベースの書換」に変更。工数は v1 比で大幅に削減。

### 既存資産（コピー済み — 書換対象）

| ファイル                                        | 現状                                  | 必要な変更                                                                                                                 |
| ------------------------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `src/mca/professors/professor_base.py`      | ProfessorBase v5.2 (73KB)、OpenAI のみ | **変更不要** — `bedrock_adapter.py` で override                                                                            |
| `src/mca/professors/prof_mirror.py`         | bookmaker 用の Mirror 教授              | `system_prompt` + `_parse_specialized_llm_output()` を MCA 仕様に書換。`prof_analyst.py` + `prof_pattern_seeker.py` のパターンを統合 |
| `src/mca/professors/prof_oracle.py`         | bookmaker 用の Oracle 教授              | `system_prompt` + 出力パーサーを MCA 仕様に書換。`prof_architect.py` の tier logic パターンを統合                                          |
| `src/mca/professors/prof_government.py`     | bookmaker 用の Government 教授          | CAPS 準拠チェック + 提案承認/却下ロジックに書換。`MCA/reflex-ledger-caps-complete.md` のルールを組み込み                                           |
| `src/mca/citadel_progression_assessment.py` | 1,978行のプロジェクト評価モジュール                | `metrics_aggregator.py` のベースとして `Status`, `Deliverable`, `Phase`, `Component` を流用                                     |

### 追加コピー済み資産（2026-02-20 — コード分析系教授5本）

| ファイル                                            | サイズ   | 現状                    | MCA での活用予定                                          | 対象 MS |
| ----------------------------------------------- | ----- | --------------------- | --------------------------------------------------- | ----- |
| `src/mca/professors/prof_code_archeologist.py`  | 4.6KB | bookmaker 用コード逆解析教授   | コードアーキテクチャ分析、設計パターン/アンチパターン検出 → Mirror 教授の強化        | MS-5  |
| `src/mca/professors/prof_code_compiler.py`      | 5.8KB | bookmaker 用メタデータ抽出教授  | ENUM/関数/スキーマ/依存関係の構造化抽出 + SHA-256 → IR メトリクス統合      | MS-5  |
| `src/mca/professors/prof_code_fixer.py`         | 2.5KB | bookmaker 用修正合成教授     | 複数分析結果からの修正合成 (diff/YAML/JSON) → proposals/executor | MS-6  |
| `src/mca/professors/prof_error_cartographer.py` | 1.1KB | bookmaker 用エラーマッピング教授 | 失敗→ソース行マッピング、システミックリスク検出 → Sentinel/Sherlock 強化     | MS-6  |
| `src/mca/professors/prof_code_ethicist.py`      | 1.1KB | bookmaker 用計算倫理教授     | 計算倫理・バイアス検出・ガバナンスパターン → SANCTUM ガバナンス検証             | MS-6  |

### 新規作成ファイル

| ファイル                                    | 内容                                                                                                                 | CGRF   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------ |
| `src/mca/__init__.py`                   | モジュール初期化                                                                                                           | Tier 1 |
| `src/mca/evolution_engine.py`           | `EvolutionEngine`: メトリクス集約 → 教授オーケストレーション → 提案生成                                                                   | Tier 1 |
| `src/mca/metrics_aggregator.py`         | `MetricsAggregator`: `citadel_progression_assessment.py` の `Status`/`Deliverable`/`Phase` をベースにコード分析 + IR メトリクスを統合 | Tier 1 |
| `src/mca/professors/bedrock_adapter.py` | `BedrockProfessorBase(ProfessorBase)`: `refine_text_with_llm()` を override して Bedrock 経由で呼び出し                      | Tier 1 |
| `src/mca/proposals/__init__.py`         | 提案パッケージ                                                                                                            | —      |
| `src/mca/proposals/models.py`           | `EvolutionProposal` (EP-CODE/EP-RAG/EP-SALES/EP-STALE/EP-GAP) — `prof_enum.py` の JSON 出力パターンを参考                    | Tier 1 |
| `src/infra/__init__.py`                 | インフラパッケージ                                                                                                          | —      |
| `src/infra/bedrock_professor_client.py` | AWS Bedrock Claude 呼び出しクライアント — `src/llm/client.py` のフォールバックパターンを参照                                                | Tier 1 |
| `src/mca/cli.py`                        | CLI: `evolve --roadmap-ir roadmap_ir.json` — `src/cgrf/cli.py` のパターンを参照                                            | Tier 1 |
| `config/mca_meta_001.yaml`              | MCA-META-001 システム憲法暫定版 — `MCA/EMERGENT_AI_METARULE.yaml` を原型に作成                                                    | —      |
| `tests/test_mca_engine.py`              | EvolutionEngine テスト（モック教授）                                                                                         | —      |
| `tests/test_mca_professors.py`          | 教授テスト（モック Bedrock）                                                                                                 | —      |
| `tests/test_mca_proposals.py`           | 提案モデルテスト                                                                                                           | —      |

### タスク

1. **`src/mca/professors/bedrock_adapter.py`** (最重要 — 新規):
   - `BedrockProfessorBase(ProfessorBase)` を定義
   - `refine_text_with_llm()` を override して `bedrock_professor_client` 経由で `us.anthropic.claude-opus-4-5-20251101-v1:0` を呼び出し
   - `professor_base.py` の OpenAI パスは温存（他用途で破壊しない）
   - `_prepare_llm_input()` / `_parse_llm_output()` は ProfessorBase のものをそのまま継承
2. **`src/infra/bedrock_professor_client.py`** (新規):
   - AWS Bedrock (boto3) 経由のクライアント
   - 環境変数: `AWS_BEDROCK_ACCESS_KEY_ID`, `AWS_BEDROCK_SECRET_ACCESS_KEY`, `AWS_BEDROCK_REGION`
   - リトライ + エクスポネンシャルバックオフ
   - `src/llm/client.py` のフォールバックパターンを参考
3. **3教授の MCA 仕様書換** (既存ファイルの書換):
   - **Mirror** (`prof_mirror.py`): `system_prompt` を MCA 仕様に変更。`code_patterns{}` + `plan_coverage{}` を出力。`prof_analyst.py` の `_extract_list_section()` + `prof_pattern_seeker.py` のコードパターン検出を統合
   - **Oracle** (`prof_oracle.py`): `system_prompt` を MCA 仕様に変更。`health_status`, `product_doc_strength`, `top_3_improvements` を出力。`prof_architect.py` の tier logic を統合
   - **Government** (`prof_government.py`): CAPS 準拠チェックに書換。`approved[]`, `rejected[]`, `risk_assessment` を出力。`MCA/reflex-ledger-caps-complete.md` のルールを組み込み。`extract_enum_tags()` を活用
4. **`src/mca/proposals/models.py`** (新規): 5種類の提案データモデル（`prof_enum.py` のパターン参考）
5. **`src/mca/metrics_aggregator.py`** (新規 — `citadel_progression_assessment.py` ベース):
   - `citadel_progression_assessment.py` から `Status`(enum+weight), `Priority`, `Deliverable`(id/name/status/phase/dependencies/blockers/completion_pct), `Phase`, `Component` を import または流用
   - `MetricsAggregator` クラス: コードメトリクスの集約（初期は手動入力、MS-5 で IR 連携）
   - `aggregate()` メソッド: 既存の `CitadelProjectDefinition` パターンを活用
6. **`src/mca/evolution_engine.py`** (新規): 7 Phase のオーケストレーション
   - Phase 1: データ収集
   - Phase 2: メタ文書読み込み（`config/mca_meta_001.yaml`）
   - Phase 3: メトリクス集約（`MetricsAggregator`）
   - Phase 4: AI 教授分析（3教授を `BedrockProfessorBase` 経由で呼出し）
   - Phase 5: 提案生成
   - Phase 6: SANCTUM 記録（MS-6 で完成）
   - Phase 7: Canonical Publisher（MS-6 で完成）
7. **`config/mca_meta_001.yaml`** (新規): `MCA/EMERGENT_AI_METARULE.yaml` を原型に MCA 用の暫定システム憲法を作成
8. **`src/mca/cli.py`** (新規): argparse CLI
9. テスト: モック Bedrock でのユニットテスト
10. **CGRF メタデータ付与**: 全新規 `.py` に Tier 1 メタデータ

### 完了基準 (全達成)

- ✅ モック Bedrock で3教授が正しくプロンプトを送信しレスポンスを解析
- ✅ `BedrockProfessorBase` が mixin として Bedrock 対応を提供
- ✅ `MetricsAggregator` がコード/プラン/Phase/IR メトリクスを統合
- ✅ EvolutionEngine が Phase 1〜7 を通過し、提案リストを生成
- ✅ EP-CODE / EP-RAG 等の提案モデルが正しくシリアライズ
- ✅ 全55テストパス
- ✅ CGRF Tier 1 全9モジュール COMPLIANT
- ✅ E2E 動作確認: `python -m src.mca.cli evolve` → 7 phases, 7 proposals, 0 errors

### 不足情報

| 不足情報                 | 影響                        | 対応策                                                           | 状態       |
| -------------------- | ------------------------- | ------------------------------------------------------------- | -------- |
| ~~**MCA-META-001**~~ | ~~Phase 2 で読み込むメタ文書~~     | ✅ `config/mca_meta_001.yaml` として暫定版を作成済み                      | **解決済み** |
| ~~**教授プロンプト**~~      | ~~出力精度~~                  | ✅ 3教授とも MCA 仕様に書換済み。実 Bedrock テストで動作確認                        | **解決済み** |
| ~~**Bedrock 接続確認**~~ | ~~実環境での動作~~               | ✅ E2E 動作確認完了 (2026-02-20)                                     | **解決済み** |
| ~~**CAPS ルール**~~     | ~~Government 教授の承認/却下基準~~ | ✅ `MCA/reflex-ledger-caps-complete.md` ベースで Government に組込み済み | **解決済み** |
| **MCA-META-001 正式版** | Phase 2 のメタ文書精度           | 暫定版で動作中。Kohei が正式版を策定後に差し替え                                   | **改善事項** |

---

## コード品質強化 (2026-02-21)

**目的**: 既存コードベースのセキュリティ脆弱性、安定性リスク、Import 矛盾を一掃し、MS-5 以降の開発基盤を堅固にする。

**完了日**: 2026-02-21
**実績**: 139 tests passed、セキュリティ脆弱性 3件修正、安定性リスク 4件修正、Import 矛盾 4ファイル修正

### セキュリティ修正

| ファイル                                   | 修正内容                                                 | 深刻度      |
| -------------------------------------- | ---------------------------------------------------- | -------- |
| `src/tools/vps_ssh.py`                 | `shlex.quote()` によるコマンドインジェクション防止                    | CRITICAL |
| `src/reflex/dispatcher.py`             | `eval()` を `ast.literal_eval()` に置換し任意コード実行を防止       | CRITICAL |
| `src/mca/professors/professor_base.py` | `random.choice()` を `secrets.choice()` に置換（暗号学的ランダム） | MEDIUM   |

### 安定性修正

| ファイル                                    | 修正内容                                                                                | 効果             |
| --------------------------------------- | ----------------------------------------------------------------------------------- | -------------- |
| `src/process_loop.py`                   | `max_runtime_seconds` + `time.monotonic()` wall-clock timeout + CLI `--max-runtime` | ポーリングループ無限実行防止 |
| `src/streaming/emitter.py`              | `_MAX_HISTORY_PER_EVENT=500`, `_MAX_COMPLETED_EVENTS=100`, `max_idle_keepalives=20` | SSE メモリリーク防止   |
| `src/skills/registry.py`                | `List` → `deque(maxlen=10000)` + ファイル読込時の行数制限                                       | 実行履歴の無制限成長防止   |
| `src/nemesis/runtime/nemesis_daemon.py` | `List` → `deque(maxlen=5000)`                                                       | ジョブ履歴の無制限成長防止  |

### Import 整理

| ファイル                           | 修正内容                                                                     |
| ------------------------------ | ------------------------------------------------------------------------ |
| `src/azure/foundry_agents.py`  | 存在しない v1 エージェント import を v2/v3 エイリアスに修正（起動時クラッシュ防止）                      |
| `src/a2a/agent_wrapper.py`     | 到達不能な v1 レガシーコード削除、`build_protocol()` を `build_protocol_v2()` のエイリアスに簡素化 |
| `src/agents/college_bridge.py` | 存在しない `src.college.service` への参照と `_try_college_service()` を削除           |
| `src/agents/council_bridge.py` | 存在しない `src.council.service` への参照と `_try_council_service()` を削除           |

> **注**: `src/college/` および `src/council/` ディレクトリは BLUEPRINT/ROADMAP のいずれにも作成予定がなく、レガシー互換コードとして残存していたため削除。

---

## MS-5: Roadmap IR × MCA 統合 ✅ 完了 (2026-02-16)

**目的**: Roadmap Translator の出力を MCA MetricsAggregator に接続し、自動フィードバックループの心臓部を構築する。

**結果**: 868 passed, 1 failed (pre-existing nemesis_v2 only)

#### 修正した3件の test_roadmap_ir_loading

- **原因**: 旧テストが生の `{"items": [], "meta": {"version": "1.0"}}` をIRファイルとして書いていた。MS-5でPhase 1がインジェスター経由でRoadmapIR Pydanticバリデーションを行うようになったため、必須フィールド（`schema_version`, `generated_at`, `sources`）が欠けてバリデーションエラーに。
- **修正**: `test_mca_engine.py:252` — 有効な RoadmapIR モデルからJSON生成し、アサーションを `["meta"]["version"]` → `["schema_version"]` / `["items_total"]` に更新。`test_evolution_engine.py` と `test_metrics_aggregator.py` は `from tests.test_mca_engine import *` プロキシなので自動的に修正済み。

#### test_nemesis_v2 の既存失敗 → 修正完了

- **エラー**: `UnicodeDecodeError: 'cp932' codec can't decode byte 0x92`
- **原因**: テストが `wrapper_path.read_text()` を `encoding` 引数なしで呼んでおり、Windows (cp932 = Shift_JIS) のデフォルトロケールエンコーディングが使われる。`agent_wrapper.py` のコメントかdocstring内にUTF-8のみでデコードできる文字（右シングル引用符 `'` = 0x92 in cp1252相当）が含まれているため、cp932デコードに失敗。
- **修正**: `read_text()` → `read_text(encoding="utf-8")` の1行変更で解消。

### 成果物

| ファイル                                                | 内容                                                                                                                               | CGRF   |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `src/integrations/roadmap_ir_ingestor.py`           | `ingest_roadmap_ir(ir_path)` → phase_completion, items_total, items_done, conflicts_count, avg_confidence, revenue_gate_coverage | Tier 1 |
| `src/integrations/roadmap_conflict_router.py`       | `conflicts[]` を Government 教授プロンプトに注入                                                                                            | Tier 1 |
| `src/integrations/roadmap_to_mca_mapper.py`         | `revenue_gate` ↔ `ZES_TIERS` マッピング                                                                                               | Tier 1 |
| `src/mca/metrics_aggregator.py` (修正)                | Roadmap IR メトリクスの取り込みを追加 — `add_roadmap_ir_metrics()` メソッド                                                                       | —      |
| `src/mca/cli.py` (修正)                               | `--roadmap-ir` フラグ対応                                                                                                             | —      |
| `src/mca/professors/prof_code_archeologist.py` (書換) | MCA 仕様に書換: コード構造逆解析 → Mirror 教授の補助分析（設計パターン/アンチパターン検出）                                                                           | Tier 1 |
| `src/mca/professors/prof_code_compiler.py` (書換)     | MCA 仕様に書換: メタデータ構造化抽出 (ENUM/関数/スキーマ/依存関係 + SHA-256) → IR メトリクス統合                                                                 | Tier 1 |
| `tests/test_prof_code_archeologist.py`              | Code Archeologist 教授テスト（モック Bedrock）                                                                                             | —      |
| `tests/test_prof_code_compiler.py`                  | Code Compiler 教授テスト（モック Bedrock）                                                                                                 | —      |
| `tests/test_roadmap_ir_ingestor.py`                 | IR 取り込みテスト                                                                                                                       | —      |
| `tests/test_integration_translate_evolve.py`        | translate → evolve の E2E テスト                                                                                                     | —      |

### タスク

1. `roadmap_ir_ingestor.py`: Blueprint §9.1 の `ingest_roadmap_ir()` を実装
   
   ```python
   def ingest_roadmap_ir(ir_path: Path) -> Dict:
       # phase_completion, items_total, items_done, items_blocked,
       # conflicts_count, avg_confidence, revenue_gate_coverage
   ```

2. `roadmap_conflict_router.py`: IR の `conflicts[]` を Government 教授のプロンプトに埋め込み

3. `roadmap_to_mca_mapper.py`: revenue_gate enum → ZES tier pricing マッピング

4. `metrics_aggregator.py` を修正: `add_roadmap_ir_metrics()` メソッド追加（`citadel_progression_assessment.py` の `Deliverable.completion_pct` と IR の `phase_completion` を統合）

5. `cli.py` を修正: `--roadmap-ir <path>` フラグを追加

6. **`prof_code_archeologist.py` MCA 書換**:
   
   - `system_prompt` を MCA 仕様に変更: コードアーキテクチャ逆解析 → 設計パターン/アンチパターン検出
   - `BedrockProfessorBase` mixin を適用
   - 出力を `Mirror` 教授の補助データとして統合（`code_patterns{}` の精度向上）
   - `_parse_specialized_llm_output()` を MCA フォーマットに書換

7. **`prof_code_compiler.py` MCA 書換**:
   
   - `system_prompt` を MCA 仕様に変更: ENUM/関数定義/スキーマ/複雑度タグ/依存関係の構造化抽出
   - `BedrockProfessorBase` mixin を適用
   - SHA-256 フィンガープリント機能を IR メトリクスと連携
   - `MetricsAggregator.add_code_structure_metrics()` メソッド追加

8. E2E テスト: 3ドキュメント → translate → `roadmap_ir.json` → evolve → proposals

9. **CGRF メタデータ付与**

### 完了基準

- `translate --in ... --out roadmap_ir.json` → `evolve --roadmap-ir roadmap_ir.json` が一気通貫で動作
- IR の metrics が教授のプロンプトに正しく反映
- conflicts が Government 教授に渡され、裁定結果が提案に反映
- E2E テストパス
- `prof_code_archeologist` が Mirror 教授の補助分析として動作し、設計パターン検出結果を出力
- `prof_code_compiler` がコード構造メタデータを抽出し、IR メトリクスに統合
- `python cgrf.py tier-check src/integrations/roadmap_ir_ingestor.py src/integrations/roadmap_conflict_router.py src/integrations/roadmap_to_mca_mapper.py src/mca/professors/prof_code_archeologist.py src/mca/professors/prof_code_compiler.py --tier 1` が全パス

### 不足情報

| 不足情報                                  | 影響                                  | 対応策                                                                                 |
| ------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------- |
| **revenue_gate → ZES tier の正確なマッピング** | `roadmap_to_mca_mapper.py` の精度      | Blueprint §9.3 のマッピング案を採用: `tradebuilder` → Scout/Operator, `zes_agent` → ZES Agent |
| **ZES プラン ($15/$20/$30) の機能一覧**       | Oracle 教授の tier feature coverage 評価 | 仮の機能一覧で実装し、Kohei が正式版を提供後に差し替え                                                      |

---

## MS-6: 提案実行 + SANCTUM ✅ 完了

**目的**: 承認された提案を自動適用し、全決定を SANCTUM に記録する。

**完了日**: 2026-02-23
**実績**: 54 tests passed (executor 15, sanctum 14, prof_code_fixer 9, prof_error_cartographer 8, prof_code_ethicist 8), 全5モジュール CGRF Tier 1 COMPLIANT

### 成果物

| ファイル                                                 | 内容                                                                       | CGRF     | テスト |
| ---------------------------------------------------- | ------------------------------------------------------------------------ | -------- | --- |
| `src/mca/proposals/executor.py`                      | 承認済み提案の自動適用 — EP-CODE/RAG/SALES/STALE/GAP + dry_run モード対応                | ✅ Tier 1 | 15  |
| `src/mca/sanctum/__init__.py`                        | SANCTUM パッケージ                                                            | ✅        | —   |
| `src/mca/sanctum/publisher.py`                       | Canonical Publisher: SHA-256 ハッシュチェーン + SANCTUM JSON 保存 + dry_run 対応     | ✅ Tier 1 | 14  |
| `.nexus/sanctum/evolution-decisions/`                | SANCTUM 記録ディレクトリ                                                         | —        | —   |
| `src/mca/professors/prof_code_fixer.py` (書換)         | MCA 仕様に書換: 複数分析結果からの修正合成 (diff/YAML/JSON) → proposals/executor の修正適用エンジン | ✅ Tier 1 | 9   |
| `src/mca/professors/prof_error_cartographer.py` (書換) | MCA 仕様に書換: 失敗→ソース行マッピング + システミックリスク検出 → Sentinel/Sherlock 強化             | ✅ Tier 1 | 8   |
| `src/mca/professors/prof_code_ethicist.py` (書換)      | MCA 仕様に書換: 計算倫理・バイアス検出・ガバナンスパターン → SANCTUM ガバナンス検証レイヤー                   | ✅ Tier 1 | 8   |
| `tests/test_prof_code_fixer.py`                      | Code Fixer 教授テスト（モック Bedrock）                                            | —        | 9   |
| `tests/test_prof_error_cartographer.py`              | Error Cartographer 教授テスト（モック Bedrock）                                    | —        | 8   |
| `tests/test_prof_code_ethicist.py`                   | Code Ethicist 教授テスト（モック Bedrock）                                         | —        | 8   |
| `tests/test_mca_executor.py`                         | 提案実行テスト (dry_run + real_write + skip ロジック)                               | —        | 15  |
| `tests/test_sanctum.py`                              | SANCTUM ハッシュチェーン + dry_run + real_write テスト                              | —        | 14  |

### タスク

1. `executor.py`（`prof_enum_to_reflex.py` のマッピングパターンを参考に設計）:
   
   - `EP-RAG-*`: Notion API 経由で新しい RAG ドラフトページを作成
   - `EP-STALE-*`: 既存ページの Sync Status を "Needs Update" に変更
   - `EP-CODE-*`: コードベースにパターンを追加（PR 作成 or ローカル修正）
   - `EP-SALES-*`: セールス文書テンプレートを Notion に作成
   - `EP-GAP-*`: カバレッジギャップのレポート生成
   - `--dry-run` モードで実際の変更なしにプレビュー

2. `sanctum/publisher.py`:
   
   - 全決定を JSON で `.nexus/sanctum/evolution-decisions/EVO-{timestamp}.json` に保存
   - 教授の洞察 + CAPS プロファイル + 提案リスト + 承認結果を含む
   - `src/audit/logger.py` のハッシュチェーンパターンを流用
   - Phase 7A (Git commit) の実装

3. **`prof_code_fixer.py` MCA 書換**:
   
   - `system_prompt` を MCA 仕様に変更: 複数分析結果（Mirror/Archeologist/Compiler）からの修正合成
   - `BedrockProfessorBase` mixin を適用
   - 出力フォーマット: diff パッチ / YAML 修正定義 / JSON 修正計画
   - `executor.py` と連携し、承認済み提案の自動修正適用をサポート

4. **`prof_error_cartographer.py` MCA 書換**:
   
   - `system_prompt` を MCA 仕様に変更: 失敗→ソース行マッピング + システミックリスクパターン検出
   - `BedrockProfessorBase` mixin を適用
   - 既存の `Sentinel` / `Sherlock` エージェントの障害分析を補強
   - エラー系統図（error lineage）の出力を `SANCTUM` 記録に統合

5. **`prof_code_ethicist.py` MCA 書換**:
   
   - `system_prompt` を MCA 仕様に変更: 計算倫理・バイアス検出・ガバナンスパターン評価
   - `BedrockProfessorBase` mixin を適用
   - SANCTUM の Phase 6 でガバナンス検証レイヤーとして機能
   - `Government` 教授の CAPS 準拠チェックと連携し、倫理面の承認/警告を追加

6. テスト: dry_run モードでの提案実行 + SANCTUM JSON の検証 + 3教授の単体テスト

7. **CGRF メタデータ付与**

### 完了基準 (全達成)

- ✅ `--dry-run` で全 EP タイプ (CODE/RAG/SALES/STALE/GAP) の提案プレビューが出力される
- ✅ SANCTUM JSON が SHA-256 ハッシュチェーンで保存される
- ✅ ハッシュチェーンで改ざん検出可能
- ✅ `prof_code_fixer` が複数分析結果から修正を合成し、executor と連携
- ✅ `prof_error_cartographer` がエラー→ソース行マッピングを出力し、SANCTUM に記録
- ✅ `prof_code_ethicist` がガバナンス検証を実行し、Government 教授と連携
- ✅ テスト全パス (54 passed)
- ✅ 全5モジュール CGRF Tier 1 パス

---

## 教授 JSON 出力統一 ✅ 完了 (2026-02-23)

**目的**: 3教授 (Mirror/Oracle/Government) の LLM 出力パーサーを JSON-first + Markdown フォールバック方式に統一し、構造化フィールドが空になるバグを恒久的に解消する。

**完了日**: 2026-02-23
**実績**: `tests/test_mca_professors.py` 28 passed (JSON 形式テスト 8件追加)

**背景**: Bedrock 実環境でのテスト時、LLM が system_prompt の指示通りに Markdown 形式で回答を返し、既存の `###` ヘッダー regex パーサーと形式がずれることで構造化フィールドが空になることを確認。Government 教授では `approved`/`rejected` が `[]` となり、11件の提案が全て pending 状態のまま executor に渡されず実行ゼロになるという致命的な連鎖障害が発生していた。

### 変更内容

| ファイル                                    | 変更内容                                                                                                                   | テスト追加 |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ----- |
| `src/mca/professors/prof_mirror.py`     | system_prompt を JSON-only 形式に変更、`_try_parse_json()` + `_normalize_json_result()` 追加、`_parse_output()` を JSON-first に変更 | +3    |
| `src/mca/professors/prof_oracle.py`     | 同上 — `health_status.overall` の保証、`top_3_improvements` の `{title, description}` 正規化も追加                                  | +2    |
| `src/mca/professors/prof_government.py` | 同上 — `approved`/`rejected`/`risk_assessment`/`conflict_arbitration` の完全正規化                                             | +3    |
| `src/infra/bedrock_professor_client.py` | `load_dotenv()` 追加 — `.env` から AWS クレデンシャルをエントリポイント依存なく確実に読み込む                                                         | —     |

### JSON パース戦略 (3段フォールバック)

```
1. 直接 json.loads() → 成功すれば即採用
2. Markdown フェンス (```json ... ```) から抽出して json.loads()
3. テキスト内の最初の { ... } ブロックを抽出して json.loads()
→ 全て失敗した場合のみ従来の Markdown セクション regex 抽出にフォールバック
```

### テスト追加 (28 total — JSON + Markdown 両形式を網羅)

| テストクラス                   | テスト数 | 内容                                   |
| ------------------------ | ---- | ------------------------------------ |
| `TestProfMirrorJSON`     | 3    | 直接 JSON / フェンス JSON / 埋め込み JSON      |
| `TestProfOracleJSON`     | 2    | 直接 JSON / フェンス JSON                  |
| `TestProfGovernmentJSON` | 3    | 直接 JSON / フェンス JSON / enum_tags 動作確認 |

---

## MS-7: Notion/Supabase/可視化 ✅ 完了

**目的**: 外部サービスとの完全な連携と、ダッシュボードでの可視化を実現する。

**完了日**: 2026-02-25
**実績**: 75 tests passed (notion_mca_client 40, supabase_mca_mirror 14, notion_bridge 21), 全4モジュール CGRF Tier 1 COMPLIANT

> **設計方針**: perplexity_control_loop_v2.py の `write_notion_page()` / `write_supabase_audit()` を設計たたき台として参照。既存の `notion_client.py` (httpx/インシデント用) および `supabase_client.py` (supabase-py SDK) と共存できるよう、MCA 専用の新規クライアントを `src/infra/` に新設。

### 成果物

| ファイル                                | 内容                                                                                                                                                                                                                       | CGRF     | テスト |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- | --- |
| `src/infra/notion_mca_client.py`    | Notion API CRUD (MCA 専用) — block builders (`_rt`, `_heading`, `_bullet`, `_code_block`, `_divider`, `_callout`) + EVO Tracker ページ作成/パッチ + ZES RAG DB クエリ/ドラフト作成/ステータス更新                                                  | ✅ Tier 1 | 40  |
| `src/infra/supabase_mca_mirror.py`  | Supabase REST ミラー (supabase-py 不要) — `automation_events` (既存) + `mca_proposals` (新規) テーブルへの書込 + 読取3関数                                                                                                                    | ✅ Tier 1 | 14  |
| `src/mca/notion_bridge.py`          | ブリッジ層 — `NotionRAGDocument`, `ZESPlanContext`, `SalesEvolutionMetrics` データクラス + `fetch_rag_documents()`, `build_zes_plan_context()`, `detect_coverage_gaps()`, `publish_evo_result()`, `create_coverage_gap_rag_pages()` | ✅ Tier 1 | 21  |
| `src/monitoring/metrics.py` (修正)    | MCA 固有 Prometheus メトリクス 4本追加 (proposals Counter, approved Counter, health_score Gauge, cycle_duration Histogram)                                                                                                         | —        | —   |
| `grafana/mca_dashboard.json`        | 9パネル MCA Evolution ダッシュボード (health gauge, health trend, proposals rate, EP-type bargauge, approved bargauge, cycle duration p50/90/99, proposal KPI stat)                                                                | —        | —   |
| `src/mca/__init__.py`               | MCA パッケージ初期化 (MS-7 新設)                                                                                                                                                                                                   | —        | —   |
| `src/infra/__init__.py` (更新)        | infra パッケージ初期化                                                                                                                                                                                                           | —        | —   |
| `tests/test_notion_mca_client.py`   | Notion 連携テスト (モック requests) — block builders, grade helpers, property extractors, create/patch/query/status 各関数                                                                                                          | —        | 40  |
| `tests/test_supabase_mca_mirror.py` | Supabase ミラーテスト (モック requests) — mirror_evo_cycle, mirror_proposals, get_recent_cycles, get_domain_health_summary                                                                                                        | —        | 14  |
| `tests/test_notion_bridge.py`       | ブリッジ層テスト — dataclasses, detect_coverage_gaps, fetch_rag_documents, build_zes_plan_context, publish_evo_result, create_coverage_gap_rag_pages                                                                             | —        | 21  |

### 追加 Prometheus メトリクス

| メトリクス名                                         | タイプ       | ラベル               |
| ---------------------------------------------- | --------- | ----------------- |
| `citadel_mca_evolution_proposals_total`        | Counter   | `domain, ep_type` |
| `citadel_mca_evolution_proposals_approved`     | Counter   | `domain`          |
| `citadel_mca_domain_health_score`              | Gauge     | `domain`          |
| `citadel_mca_evolution_cycle_duration_seconds` | Histogram | —                 |

### 完了基準 (全達成)

- ✅ Notion からドキュメント一覧が取得できる (dry_run + モック tests)
- ✅ カバレッジギャップが正しく検出される (domain/ep_type × min_coverage 閾値)
- ✅ Supabase にメトリクスが保存される (dry_run + モック tests)
- ✅ Grafana で MCA メトリクスが可視化される (9パネルダッシュボード)
- ✅ CGRF Tier 1 全モジュール COMPLIANT
- ✅ 75 tests passed (regression 0)
- ✅ `NOTION_TOKEN` / `SUPABASE_URL` 未設定時はログ警告 + None/[] でグレースフルスキップ

### 実装上のキーポイント

- `notion_mca_client.py` は `requests` ベース (既存の httpx ベース `notion_client.py` と共存)
- `supabase_mca_mirror.py` は REST API 直呼び (既存の supabase-py ベース `SupabaseStore` と共存)
- `dry_run=True` で外部 API 呼出しをスキップ、テストでも活用可能
- スコアグレード変換: 90→S, 75→A, 60→B, 45→C, 0→D (callout 色・絵文字と連動)
- `publish_evo_result()` が Notion ページ作成 → Supabase cycle 行 → Supabase proposals 行の順で実行

---

## MS-8: 汎用拡張 + GGUF + CI 統合

**✅ 完了 (2026-02-27) — 49 tests passed**

**目的**: Translator の拡張性を高め、GGUF ローカル推論を有効化し、CI/CD パイプラインに統合する。

### 成果物

| ファイル                                                     | 内容                                            | CGRF     | テスト |
| -------------------------------------------------------- | --------------------------------------------- | -------- | --- |
| `src/roadmap_translator/translators/generic_markdown.py` | 汎用 Markdown Translator (allowlist 外は unknown) | ✅ Tier 1 | 25  |
| `src/roadmap_translator/translators/gitlog.py`           | git log → commit-phase マッピング                  | ✅ Tier 1 | —   |
| `src/roadmap_translator/enricher.py`                     | GGUF による要約・リスクノート・推薦生成                        | ✅ Tier 1 | —   |
| `src/roadmap/gguf_engine.py`                             | llama-cpp-python GGUF エンジン + ルールベースフォールバック    | ✅ Tier 1 | 24  |
| `ci/translate_evolve_publish.sh`                         | CI 統合スクリプト: translate → evolve → publish      | —        | —   |
| `tests/test_generic_markdown_translator.py`              | 汎用 Translator テスト                             | —        | 25  |
| `tests/test_gguf_engine.py`                              | GGUF エンジンテスト (ルールベース)                         | —        | 24  |

### 修正ファイル

| ファイル                                 | 変更内容                                                     |
| ------------------------------------ | -------------------------------------------------------- |
| `src/roadmap_translator/detect.py`   | `GitlogTranslator` + `GenericMarkdownTranslator` 検出ルール追加 |
| `src/roadmap_translator/pipeline.py` | `DEFAULT_TRANSLATORS` に 2 Translator 追加                  |

### 完了基準（全達成）

- ✅ 汎用 Markdown ファイルが `generic_markdown.py` で items に変換される
- ✅ git log の commit が phase にマッピングされる (`FILE_PHASE_MAP`)
- ✅ GGUF エンジンがモデル有無で自動切替 (`_HAS_LLAMA` フラグ)
- ✅ CI スクリプトが GitHub Actions / GitLab CI 両対応
- ✅ CGRF Tier 1 パス (全4モジュール)
- ✅ 49 tests passed

---

## コード品質強化 (2026-02-28) ✅ 完了

**目的**: MS-8 完了後に発見された契約インターフェース不一致と Python deprecation warning を一掃し、フルスイートをクリーンな状態にする。

**完了日**: 2026-02-28
**実績**: 1133 tests passed (full suite), deprecation warning 0件

### Event JSON v1 契約修正

commit `79f5497` (contracts/sentinel/services) + `87e2bab` (Fix Event Contract Event JSON v1) で追加された A2A ハンドオフ契約の **インターフェース不一致** (13テスト失敗) を修正。

| ファイル                                       | 修正内容                                                                                                                                                                                                 |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/contracts/handoff_packet.py`          | フィールドを `id`/`source`/`destination` → `source_agent_id`/`target_agent_id`/`payload` に刷新。`validate()` をインスタンスメソッド + jsonschema 検証に変更（構造チェックのみ。空文字列は型有効）。`from_dict()` は jsonschema.ValidationError を送出 |
| `src/contracts/handoff_packet_contract.py` | フィールドを `id`/`timestamp`/`payload` (全て `Optional`, None 時は `__post_init__` で `ValueError("Missing required fields: [...]")`) に刷新。`to_json()` メソッドを追加                                                  |
| `src/contracts/decision_contract.py`       | timestamp 検証を厳格化: `'T'` セパレータ必須（`"2023-10-01 12:00:00"` 形式を拒否）                                                                                                                                       |
| `tests/contracts/test_handoff_packet.py`   | 旧インターフェース（ValueError 期待）から新インターフェース（jsonschema.ValidationError 期待）に更新                                                                                                                                |

### datetime.utcnow() 一掃

Python 3.12+ で deprecated となった `datetime.utcnow()` を全13ファイルで `datetime.now(timezone.utc)` に置換。`timezone` インポートも自動追加。

| 置換パターン                                | 修正後                                                             |
| ------------------------------------- | --------------------------------------------------------------- |
| `datetime.utcnow().isoformat() + "Z"` | `datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')` |
| `datetime.utcnow().isoformat()`       | `datetime.now(timezone.utc).isoformat()`                        |
| `datetime.utcnow().strftime(...)`     | `datetime.now(timezone.utc).strftime(...)`                      |
| `datetime.utcnow()` (オブジェクト)          | `datetime.now(timezone.utc)`                                    |

影響ファイル: `src/agents/fixer_v3.py`, `guardian_v3.py`, `sherlock_v3.py`, `sentinel_v2.py`, `src/audit/report.py`, `src/approval/request.py`, `src/approval/response.py`, `src/types.py`, `src/nemesis/pentest_engine.py`, `src/nemesis/runtime/nemesis_daemon.py`, `src/nemesis/deploy/nemesis_cli.py`, `src/mike/engine/metadata_writer.py`, `tests/test_nemesis_runtime.py`

---

## マイルストン間の依存関係マトリクス

```
         MS-1  MS-2  MS-3  MS-4  MS-5  MS-6  MS-7  MS-8
MS-1      -     →     →     →     →     →     →     →
MS-2            -     →           →                 →
MS-3                  -                       →
MS-4                        -     →     →     →
MS-5                              -     →
MS-6                                    -     →
MS-7                                          -
MS-8                                                -
```

| 依存          | 説明                               |
| ----------- | -------------------------------- |
| MS-1 → 全て   | スキーマが全モジュールの基盤                   |
| MS-2 → MS-3 | Tracker は IR を読む                 |
| MS-2 → MS-5 | IR ingestor は IR を消費             |
| MS-4 → MS-5 | MCA エンジンに IR メトリクスを注入            |
| MS-4 → MS-6 | 提案実行は提案モデルに依存                    |
| MS-5 → MS-6 | 統合後に実行層を構築                       |
| MS-6 → MS-7 | Notion 実行は executor に依存          |
| MS-2 → MS-8 | 汎用 Translator は基盤 Translator に依存 |

---

## 並行開発が可能な組み合わせ

| 並行A                    | 並行B            | 理由                     |
| ---------------------- | -------------- | ---------------------- |
| MS-2 (Translator)      | MS-4 (MCA コア)  | 両方とも MS-1 に依存するが、互いに独立 |
| MS-3 (Tracker/API)     | MS-4 (MCA コア)  | 同上                     |
| MS-7 (Notion/Supabase) | MS-8 (汎用/GGUF) | MS-6 完了後に並行可能          |

**推奨開発順序**:

1. ~~MS-1 を最優先で完成~~ ✅ 完了 (2026-02-20)
2. ~~MS-2 ✅ 完了 (2026-02-20) と MS-4 ✅ 完了 (2026-02-20) を **並行** 開発~~
3. ~~MS-3 ✅ 完了 (2026-02-22) と MS-5 ✅ 完了 (2026-02-16) を開発~~
4. ~~MS-6 ✅ 完了 (2026-02-23) — 54 tests passed~~
5. ~~教授 JSON 出力統一 ✅ 完了 (2026-02-23) — 28 tests passed~~
6. ~~MS-7 ✅ 完了 (2026-02-25) — 75 tests passed~~
7. ~~MS-8 ✅ 完了 (2026-02-27) — 49 tests passed~~
8. ~~コード品質強化 (Event JSON v1 + datetime) ✅ 完了 (2026-02-28) — 1133 passed (full suite)~~

---

## 修正対象ファイル一覧（既存ファイルの変更箇所）

| 既存ファイル                                          | 変更内容                                               | マイルストン            |
| ----------------------------------------------- | -------------------------------------------------- | ----------------- |
| `src/app.py`                                    | `roadmap_router` のマウント追加、`/mca/*` ルーターのマウント追加      | MS-3, MS-4        |
| `src/config.py`                                 | Bedrock 教授設定、GGUF モデルパス、Roadmap Translator 設定の追加   | MS-2, MS-4        |
| `citadel.config.yaml`                           | `roadmap:`, `mca:`, `bedrock_professors:` セクションの追加 | MS-2, MS-4        |
| `src/mca/professors/prof_mirror.py`             | MCA 仕様に system_prompt + 出力パーサーを書換                  | MS-4              |
| `src/mca/professors/prof_oracle.py`             | MCA 仕様に system_prompt + 出力パーサーを書換                  | MS-4              |
| `src/mca/professors/prof_government.py`         | CAPS 準拠チェック + 提案承認/却下に書換                           | MS-4              |
| `src/mca/professors/prof_code_archeologist.py`  | MCA 仕様に書換: コード構造逆解析 → Mirror 補助分析                  | MS-5 ✅            |
| `src/mca/professors/prof_code_compiler.py`      | MCA 仕様に書換: メタデータ構造化抽出 → IR メトリクス統合                 | MS-5 ✅            |
| `src/mca/professors/prof_code_fixer.py`         | MCA 仕様に書換: 修正合成 → executor 連携                      | MS-6              |
| `src/mca/professors/prof_error_cartographer.py` | MCA 仕様に書換: エラーマッピング → Sentinel/Sherlock 強化         | MS-6              |
| `src/mca/professors/prof_code_ethicist.py`      | MCA 仕様に書換: ガバナンス検証 → SANCTUM 連携                    | MS-6              |
| `src/mca/metrics_aggregator.py`                 | `add_roadmap_ir_metrics()` メソッド追加                  | MS-5 ✅            |
| `src/mca/cli.py`                                | `--roadmap-ir` フラグ対応                               | MS-5 ✅            |
| `src/monitoring/metrics.py`                     | MCA 固有 Prometheus メトリクスの追加                         | MS-7 ✅            |
| `src/integrations/`                             | `roadmap_ir_ingestor.py` 等の新規ファイル追加                | MS-5 ✅            |
| `.gitignore`                                    | `models/*.gguf`, `.nexus/sanctum/` の追加             | MS-1 ✅            |
| `src/contracts/handoff_packet.py`               | Event JSON v1: フィールド刷新 + validate() インスタンスメソッド化    | 品質強化 2026-02-28 ✅ |
| `src/contracts/handoff_packet_contract.py`      | Event JSON v1: フィールド刷新 + to_json() 追加              | 品質強化 2026-02-28 ✅ |
| `src/contracts/decision_contract.py`            | timestamp 'T' セパレータ必須化                             | 品質強化 2026-02-28 ✅ |
| `tests/contracts/test_handoff_packet.py`        | 新インターフェースに合わせてテスト更新                                | 品質強化 2026-02-28 ✅ |
| `src/agents/*.py`, `src/audit/*.py` 他 13 ファイル   | `datetime.utcnow()` → `datetime.now(timezone.utc)` | 品質強化 2026-02-28 ✅ |

---

## 新規作成ファイル一覧（全マイルストン合計）

### P0（必須、MS-1〜MS-5）: 約30ファイル

```
src/roadmap_ir/__init__.py                                   ✅ MS-1
src/roadmap_ir/schema.json                                   ✅ MS-1
src/roadmap_ir/types.py                                      ✅ MS-1
src/roadmap_ir/validators.py                                 ✅ MS-1
src/roadmap_translator/__init__.py                           ✅ MS-2
src/roadmap_translator/cli.py                                ✅ MS-2
src/roadmap_translator/pipeline.py                           ✅ MS-2
src/roadmap_translator/ingest.py                             ✅ MS-2
src/roadmap_translator/detect.py                             ✅ MS-2
src/roadmap_translator/normalize.py                          ✅ MS-2
src/roadmap_translator/merge.py                              ✅ MS-2
src/roadmap_translator/emit.py                               ✅ MS-2
src/roadmap_translator/translators/__init__.py               ✅ MS-2
src/roadmap_translator/translators/base.py                   ✅ MS-2
src/roadmap_translator/translators/readme.py                 ✅ MS-2
src/roadmap_translator/translators/markdown_roadmap.py       ✅ MS-2
src/roadmap_translator/translators/implementation_summary.py ✅ MS-2
src/roadmap/__init__.py
src/roadmap/models.py
src/roadmap/tracker.py
src/roadmap/api.py
src/mca/__init__.py                                         ✅ MS-4
src/mca/cli.py                                              ✅ MS-4
src/mca/evolution_engine.py                                 ✅ MS-4
src/mca/metrics_aggregator.py                               ✅ MS-4
src/mca/professors/__init__.py                              ✅ MS-4
src/mca/professors/bedrock_adapter.py                       ✅ MS-4
src/mca/professors/prof_mirror.py (書換)                      ✅ MS-4
src/mca/professors/prof_oracle.py (書換)                      ✅ MS-4
src/mca/professors/prof_government.py (書換)                  ✅ MS-4
src/mca/proposals/__init__.py                               ✅ MS-4
src/mca/proposals/models.py                                 ✅ MS-4
src/infra/__init__.py                                       ✅ MS-4
src/infra/bedrock_professor_client.py                       ✅ MS-4
src/integrations/roadmap_ir_ingestor.py                     ✅ MS-5
config/roadmap_translate.toml                               ✅ MS-2
config/mca_meta_001.yaml                                    ✅ MS-4
```

### P1（重要、MS-5〜MS-7）: 約15ファイル

```
src/integrations/roadmap_conflict_router.py                     ✅ MS-5
src/integrations/roadmap_to_mca_mapper.py                       ✅ MS-5
src/mca/professors/prof_code_archeologist.py (書換)              ✅ MS-5
src/mca/professors/prof_code_compiler.py (書換)                  ✅ MS-5
src/mca/professors/prof_code_fixer.py (書換)                     MS-6
src/mca/professors/prof_error_cartographer.py (書換)             MS-6
src/mca/professors/prof_code_ethicist.py (書換)                  MS-6
src/mca/proposals/executor.py
src/mca/sanctum/__init__.py
src/mca/sanctum/publisher.py
src/mca/professors/prof_code_fixer.py (書換)                     ✅ MS-6
src/mca/professors/prof_error_cartographer.py (書換)             ✅ MS-6
src/mca/professors/prof_code_ethicist.py (書換)                  ✅ MS-6
src/mca/proposals/executor.py                                   ✅ MS-6
src/mca/sanctum/__init__.py                                     ✅ MS-6
src/mca/sanctum/publisher.py                                    ✅ MS-6
src/mca/__init__.py                                             ✅ MS-7
src/mca/notion_bridge.py                                        ✅ MS-7
src/infra/notion_mca_client.py                                  ✅ MS-7
src/roadmap_translator/translators/generic_markdown.py          ✅ MS-8
src/roadmap_translator/translators/gitlog.py                    ✅ MS-8
```

### P2（拡張、MS-7〜MS-8）: 約5ファイル

```
src/roadmap_translator/enricher.py                              ✅ MS-8
src/roadmap/gguf_engine.py                                      ✅ MS-8
src/infra/supabase_mca_mirror.py                                ✅ MS-7
src/infra/nexus_url_publisher.py                                (MS-8)
grafana/mca_dashboard.json                                      ✅ MS-7
```

### テスト: 約20ファイル

```
tests/test_roadmap_ir_schema.py                ✅ MS-1 (31 tests)
tests/test_translator_readme.py                ✅ MS-2 (8 tests)
tests/test_translator_roadmap.py               ✅ MS-2 (7 tests)
tests/test_translator_impl_summary.py          ✅ MS-2 (8 tests)
tests/test_translator_merge.py                 ✅ MS-2 (8 tests)
tests/test_translator_pipeline.py              ✅ MS-2 (4 tests)
tests/test_translator_determinism.py           ✅ MS-2 (2 tests)
tests/test_roadmap_tracker.py
tests/test_roadmap_api.py
tests/test_mca_engine.py                      ✅ MS-4 (18 tests)
tests/test_mca_professors.py                  ✅ MS-4+JSON統一 (28 tests — JSON 8件追加)
tests/test_mca_proposals.py                   ✅ MS-4 (16 tests)
tests/test_evolution_engine.py                ✅ MS-4 (CGRF proxy)
tests/test_metrics_aggregator.py              ✅ MS-4 (CGRF proxy)
tests/test_bedrock_adapter.py                 ✅ MS-4 (CGRF proxy)
tests/test_bedrock_professor_client.py        ✅ MS-4 (CGRF proxy)
tests/test_prof_mirror.py                     ✅ MS-4 (CGRF proxy)
tests/test_prof_oracle.py                     ✅ MS-4 (CGRF proxy)
tests/test_prof_government.py                 ✅ MS-4 (CGRF proxy)
tests/test_models.py                          ✅ MS-4 (CGRF proxy)
tests/test_prof_code_archeologist.py                         ✅ MS-5
tests/test_prof_code_compiler.py                             ✅ MS-5
tests/test_prof_code_fixer.py                                ✅ MS-6 (9 tests)
tests/test_prof_error_cartographer.py                        ✅ MS-6 (8 tests)
tests/test_prof_code_ethicist.py                             ✅ MS-6 (8 tests)
tests/test_roadmap_ir_ingestor.py                            ✅ MS-5
tests/test_integration_translate_evolve.py                   ✅ MS-5
tests/test_sanctum.py                                        ✅ MS-6 (14 tests)
tests/test_notion_mca_client.py                              ✅ MS-7 (40 tests)
tests/test_supabase_mca_mirror.py                            ✅ MS-7 (14 tests)
tests/test_notion_bridge.py                                  ✅ MS-7 (21 tests)
tests/test_generic_markdown_translator.py                    ✅ MS-8 (25 tests)
tests/test_gguf_engine.py                                    ✅ MS-8 (24 tests)
```

---

## v2 でのスコープ変化のまとめ

### 工数削減（教授ベースのコピー済み資産により）

| 項目                   | v1 の想定                      | v2 の実態                                                                                    |
| -------------------- | --------------------------- | ----------------------------------------------------------------------------------------- |
| `professors/base.py` | ゼロから ABC 設計 + Bedrock 呼出し   | `professor_base.py` v5.2 (73KB) が完成品。`bedrock_adapter.py` で override するだけ                 |
| 3教授                  | ゼロから設計                      | コピー済みの `prof_*.py` の system_prompt + 出力パーサーを書換のみ                                          |
| MetricsAggregator    | ゼロからデータモデル設計                | `citadel_progression_assessment.py` の `Status`/`Deliverable`/`Phase`/`Component` がそのまま使える |
| MCA-META-001         | 暫定テンプレートをゼロから               | `MCA/EMERGENT_AI_METARULE.yaml` (44KB) が原型                                                |
| CAPS ルール             | `src/ags/caps_stub.py` から推測 | `MCA/reflex-ledger-caps-complete.md` (96KB) が正式ルール                                        |

### 追加された品質要件

| 要件                 | 影響                                                                                  |
| ------------------ | ----------------------------------------------------------------------------------- |
| **CGRF Tier 1 準拠** | 全新規 `.py` に docstring + `_MODULE_NAME`/`_MODULE_VERSION`/`_CGRF_TIER` + テストファイルを義務化 |
| **CGRF バリデーション**   | 各 MS の完了基準に `python cgrf.py validate --tier 1` パスを追加                                |

---

## 全体の不足情報サマリ（Kohei への確認事項）

### ~~優先度: 高~~ → 解決済み / 仮対応済み

1. ~~**Phase 19〜27 の revenue_gate マッピング**~~: **仮マッピング確定済み**（Blueprint §4.2 参照）。Phase 19-24,26 = `core`, Phase 25 = `zes_agent`, Phase 27 = `tradebuilder`。Kohei の正式承認後に差し替え
2. ~~**AWS Bedrock 接続テスト**~~: **✅ 確認完了** (2026-02-19, `test_bedrock.py` で疎通成功)

### 優先度: 中（MS-5〜MS-6 で必要だが暫定対応可能）

3. **MCA-META-001 システム憲法の正式版**: ✅ 暫定版 (`config/mca_meta_001.yaml`) で MS-4 動作確認済み。正式版は Kohei が策定
4. **CAPS プロトコルの教授版ルールの最終確認**: ✅ Government 教授に組込み済み、E2E テストで承認/却下の動作確認済み。妥当性の最終確認を Kohei に依頼
5. **Notion API トークン + Database ID 確認**: ✅ `NOTION_TOKEN` 未設定時はログ警告 + None/[] でグレースフルスキップ実装済み。実環境接続は ENV 設定のみで有効化可能
6. **ZES プラン機能一覧**: Oracle 教授の精度に影響

### 優先度: 低（MS-8 で必要）

7. **Supabase プロジェクト情報**: ✅ `SUPABASE_URL` 未設定時のグレースフルスキップ実装済み。実環境接続は ENV 設定のみで有効化可能
8. **Citadel Nexus URL API 仕様**: スタブで開発可能
9. **GitLab リポジトリ情報**: ローカル Git で開発可能
10. **GGUF モデル選定**: 環境変数で切替可能な設計のため後回し可能

---

*Generated: 2026-02-19 v2 — Updated: 2026-02-28 (Event JSON v1 契約修正 + datetime deprecation 一掃 — 1133 tests passed) — Citadel Lite Evolution Roadmap*
