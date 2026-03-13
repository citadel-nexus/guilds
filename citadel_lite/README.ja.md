# Citadel Lite — 自律型AIオペレーティングシステム

[English](README.md)

**Microsoft AI Dev Days Hackathon 2026** — すべての6カテゴリーを制覇することを目指す

| カテゴリー                             | 実装の詳細                                                      |
| ------------------------------------ | ----------------------------------------------------------- |
| **AIアプリケーションとエージェント**         | ZES AI従業員、Watcherライブモニタリングエージェント、MCP音声統合  |
| **エージェント型DevOps**                   | OADループ: 検出 → 診断 → 修復 → ガバナンス → 自己回復          |
| **Microsoft Foundryの最適な利用**    | すべての4つのコアエージェントがAzure Foundryエージェントサービスを介して動作 |
| **最優秀エンタープライズソリューション**         | ZES SaaS: スカウト ¥2,200/月 · オペレーター ¥2,900/月 · オートパイロット ¥4,400/月 |
| **最優秀マルチエージェントシステム**          | A2Aプロトコル上の5エージェント、型付きHandoffPacketによるハンドオフ |
| **最優秀Azure統合**           | Foundry + Azure OpenAI + Cosmos DBメモリ + Service Busイベント       |

**Microsoft AI Dev Days Hackathon — エージェント型DevOpsカテゴリー**

Citadel Liteは、CI/CDの失敗を検出し、根本原因を診断し、修正を提案し、ガバナンスを強制し、修復を実行する閉ループのマルチエージェントDevOpsパイプラインです。これらすべては、改ざん防止の監査証跡と責任あるAIポリシーに伴っています。

**最新の実装 (2026-03-06)**:

- ✅ **VCC × OAD × Perplexity統合完了** - MS-A1からA7 + MS-B1からB3 + MS-C1からC3がすべて実装され、177テストに合格 (BLUEPRINT v9.0)
- ✅ **Nemesis防御システム** - L2インスペクター / L3ハニーポット / L4オラクル + 管理APIが完了 (MS-B1からB3)
- ✅ **VCCSakeReader + CAPSグレード統合** - `.sake`プロファイルの読み込み + T1からT5のグレードマッピング (MS-C3)
- ✅ **DiagnosticsLoop** - READ→THINK→WRITE→ASSESSの4ステップ診断ループ + OrchestratorV3のワイヤーイン (MS-A3/A6)
- ✅ **Datadogアダプター** - ループ実行結果の外部可視化の発信 (MS-A5)
- ✅ **CGRF CLAUDE.md + 監査スクリプト** - cgrf_audit.pyを介したすべてのモジュールの自動監査 (MS-C1)
- ✅ **Notion SMPレジストリDB** - Notionとのモジュールメタデータの同期 (MS-C2)
- ✅ **コード品質の向上** - イベントJSON v1 A2A契約の修正 + 非推奨API `datetime.utcnow()`の排除 (2026-02-28)
- ✅ **Notion/Supabase可視化統合** - Notion MCAブロック + Supabase RESTミラー + Grafana 9パネルMCAダッシュボード (MS-7)
- ✅ **汎用Markdown + Gitlog変換 + GGUF強化** - GenericMarkdownTranslator / GitlogTranslator + ローカル推論 + CIスクリプト (MS-8)
- ✅ **ロードマップトラッカー & API** - IRスナップショット + ファイナンスギルドレポート + 健康エンドポイント (MS-3)
- ✅ **セキュリティ強化** - コマンドインジェクション防止 (shlex.quote)、eval()の排除 (ast.literal_eval)、暗号的ランダム性 (secrets.choice)
- ✅ **安定性の向上** - 実時間タイムアウト、SSEメモリリーク防止、無制限データ構造 (deque) の上限設定
- ✅ **MCA進化エンジン** - 7Phase AI教育オーケストレーション + 自動提案生成 (MS-4)
- ✅ **AWS Bedrock統合** - 3つのMCA教育 (ミラー/オラクル/政府) がClaude Opus 4.5を介して運用中
- ✅ **VS Code拡張機能** - CGRF TierのリアルタイムIDE検証 (フェーズ27)
- ✅ **モニタリング & 可視化** - Prometheus 16メトリクス (12+4 MCA) + Grafanaダッシュボードが完成 (フェーズ26)
- ✅ **AIS XP/TP経済** - デュアルトークン経済エンジンが完成 (フェーズ25)
- ✅ **AGSパイプライン** - 4段階の憲法司法パイプラインが完成 (フェーズ24)
- ✅ **CGRF v3.0 Tier 2達成** - すべての4エージェントが生産レベルに到達
- ✅ **自動実行 & 自動マージ** - リスクベースの完全自動システム (フェーズ22)
- ✅ **REFLEX自己修復** - 検証失敗時の自動再試行機能
- ✅ **1310テスト合格** - フルスイート (2026-03-06時点で、+177の新しいテスト)

---

## 構造
```
citadel-lite/
├── config/                        # 設定ファイル
│   ├── azure.yaml.example
│   └── settings.yaml              # 自動実行、AGS、AIS、監視設定
├── grafana/                       # Grafana ダッシュボード (フェーズ 26, MS-7)
│   ├── citadel_dashboard.json     # Prometheus ダッシュボード (11 パネル)
│   └── mca_dashboard.json         # ✨ MCA 9 パネル Grafana ダッシュボード (MS-7)
├── ci/                            # ✨ CI スクリプト (MS-8)
│   └── translate_evolve_publish.sh  # translate→evolve→publish バッチ実行
├── old/                           # レガシーファイルバックアップ (V2→V3 統合)
│   ├── orchestrator_v2.py
│   ├── orchestrator.py
│   ├── store.py
│   ├── runner.py
│   ├── sherlock.py
│   └── fixer.py
│
├── vscode-extension/              # ✨ VS Code 拡張機能 (フェーズ 27)
│   └── citadel-cgrf/
│       ├── package.json           # 拡張機能マニフェスト
│       ├── src/                   # TypeScript ソース (拡張機能、cgrfRunner、statusBar など)
│       └── test/                  # 拡張機能テスト
│
├── demo/
│   ├── events/
│   │   ├── ci_failed.sample.json
│   │   ├── deploy_failure.sample.json
│   │   └── security_alert.sample.json
│   └── run_demo.py
├── docs/                          # ✨ 新規: ドキュメント
│   └── AUTO_EXECUTION.md          # ✨ 新規: 自動実行ガイド
│
├── src/
│   ├── types.py                    # CGRFMetadata データクラスを追加 (v3.0)
│   ├── orchestrator_v3.py          # リトライ検証 + REFLEX 自己修復
│   ├── app.py
│   ├── process_loop.py
│   │
│   ├── agents/
│   │   ├── sentinel_v2.py          # CGRF Tier 1 メタデータ
│   │   ├── sherlock_v3.py          # CGRF Tier 1 メタデータ
│   │   ├── fixer_v3.py             # CGRF Tier 1 メタデータ
│   │   └── guardian_v3.py          # CGRF Tier 2 メタデータ
│   │
│   ├── ags/                        # ✨ AGS パイプライン (フェーズ 24)
│   │   ├── __init__.py             # パッケージ初期化 & 公開 API
│   │   ├── caps_stub.py            # CAPS グレーディング (D/C/B/A/S) + AIS ブリッジ
│   │   ├── s00_generator.py        # S00: 意図の正規化 → SapientPacket
│   │   ├── s01_definer.py          # S01: スキーマ + CAPS ティア検証
│   │   ├── s02_fate.py             # S02: 5 ポリシーゲート → ALLOW/REVIEW/DENY
│   │   ├── s03_archivist.py        # S03: 監査ハッシュチェーン記録
│   │   └── pipeline.py             # AGSPipeline ランナー (S00→S01→S02→S03)
│   │
│   ├── ais/                        # ✨ 新規: AIS XP/TP 経済 (フェーズ 25)
│   │   ├── __init__.py             # パッケージ初期化 & 公開 API
│   │   ├── profile.py              # AgentProfile (XP/TP トラッキング、CAPS 変換)
│   │   ├── storage.py              # ProfileStore (ファイルベースの JSON 永続性)
│   │   ├── costs.py                # CostTable (アクション TP コスト)
│   │   ├── rewards.py              # RewardCalculator (ティア乗数、ボーナス)
│   │   └── engine.py               # AISEngine (予算、報酬、支出)
│   │
│   ├── monitoring/                 # ✨ 新規: 監視 & 可観測性 (フェーズ 26)
│   │   ├── __init__.py             # パッケージ初期化 & 公開 API 再エクスポート
│   │   ├── metrics.py              # 12 の Prometheus メトリクス + フェイルオープン記録
│   │   └── middleware.py           # オプションの FastAPI HTTP ミドルウェア
│   │
│   ├── cgrf/                       # CGRF CLI バリデーター
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py                  # 3 コマンド: validate/tier-check/report
│   │   ├── validator.py            # ティア 0-3 検証ロジック
│   │   └── README.md               # CGRF CLI ドキュメント
│   │
│   ├── a2a/
│   │   ├── protocol.py
│   │   └── agent_wrapper.py
│   │
│   ├── llm/
│   │   ├── client.py
│   │   └── prompts.py
│   │
│   ├── memory/
│   │   ├── store_v2.py             # RAG メモリ (古い store.py は old/ にバックアップ)
│   │   ├── vector_store.py         # FAISS ベクトルメモリ
│   │   └── corpus.json
│   │
│   ├── execution/
│   │   ├── runner_V2.py            # verify_results.json を生成 (古い runner.py は old/ にバックアップ)
│   │   └── outcome_store.py
│   │
│   ├── audit/
│   │   ├── report.py               # CGRF メタデータ出力を追加
│   │   └── logger.py
│   │
│   ├── approval/
│   │   ├── request.py
│   │   └── response.py
│   │
│   ├── governance/
│   │   ├── policies.yaml
│   │   └── policy_engine.py
│   │
│   ├── reflex/
│   │   ├── manifest.yaml
│   │   └── dispatcher.py
│   │
│   ├── ingest/
│   │   ├── normalizer.py
│   │   ├── webhook.py
│   │   └── outbox.py
│   │
│   ├── github/
│   │   └── client.py               # ✨ 更新: CI 待機 + 自動マージ
│   │
│   ├── streaming/
│   │   └── emitter.py
│   │
│   ├── mcp_server/
│   │   └── server.py
│   │
│   ├── dashboard/
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   │
│   ├── azure/
│   │   ├── config.py
│   │   ├── servicebus_adapter.py
│   │   ├── foundry_agents.py
│   │   ├── cosmos_memory.py
│   │   └── telemetry.py
│   │
│   ├── roadmap_ir/                    # ✨ ロードマップ IR スキーマ (MS-1)
│   │   ├── schema.json               # JSON スキーマドラフト 2020-12
│   │   ├── types.py                   # Pydantic v2 モデル
│   │   └── validators.py             # セマンティック検証
│   │
│   ├── roadmap_translator/            # ✨ ロードマップトランスレーター (MS-2)
│   │   ├── cli.py                     # translate --in ... --out ...
│   │   ├── pipeline.py                # Ingest→Detect→Translate→Normalize→Merge→Validate→Emit
│   │   ├── enricher.py                # ✨ IR エンリッチ (GGUF/ルールベース) (MS-8)
│   │   ├── detect.py                  # ✨ ジェネリック/Gitlog フォールバック検出 (MS-8)
│   │   └── translators/
│   │       ├── readme.py              # README 最新の実装 → アイテム
│   │       ├── markdown_roadmap.py    # フェーズ N: → アイテム
│   │       ├── implementation_summary.py  # 実装サマリー → アイテム
│   │       ├── generic_markdown.py    # ✨ ジェネリック Markdown フォールバック (MS-8)
│   │       └── gitlog.py              # ✨ git log → EvidenceGit アイテム (MS-8)
│   │
│   ├── roadmap/                       # ✨ ロードマップユーティリティ (MS-8)
│   │   └── gguf_engine.py             # GGUF ローカル推論 + ルールベースフォールバック
│   │
│   ├── mca/                           # ✨ MCA エボリューションエンジン (MS-4/MS-7)
│   │   ├── cli.py                     # evolve --meta ... --dry-run
│   │   ├── evolution_engine.py        # 7 フェーズオーケストレーション
│   │   ├── metrics_aggregator.py      # 統一メトリクススナップショット
│   │   ├── notion_bridge.py           # ✨ Notion/Supabase ブリッジ (MS-7)
│   │   ├── professors/               # ミラー、オラクル、政府 (Bedrock)
│   │   │   ├── bedrock_adapter.py     # BedrockProfessorBase ミックスイン
│   │   │   ├── prof_mirror.py         # コードパターン + カバレッジ分析
│   │   │   ├── prof_oracle.py         # 戦略的ガイダンス + 健康
│   │   │   └── prof_government.py     # CAPS 準拠 + 提案ガバナンス
│   │   └── proposals/
│   │       └── models.py              # EP-CODE/RAG/SALES/STALE/GAP
│   │
│   ├── contracts/                     # ✨ A2A イベント JSON v1 コントラクト (修正)
│   │   ├── handoff_packet.py          # HandoffPacket と jsonschema 検証
│   │   ├── handoff_packet_contract.py # __post_init__ 必須フィールドチェック
│   │   └── decision_contract.py       # ISO 8601 'T' セパレーター強制
│   │
│   └── infra/                         # ✨ インフラストラクチャ (MS-4/MS-7)
│       ├── bedrock_professor_client.py  # AWS Bedrock Claude クライアント
│       ├── notion_mca_client.py         # ✨ Notion API (EVO トラッカー、ZES RAG DB) (MS-7)
│       └── supabase_mca_mirror.py       # ✨ Supabase REST ミラー (MS-7)
│
├── tests/
│   ├── test_sentinel_v2.py        # ティア 1 ユニットテスト (9 テスト)
│   ├── test_sherlock_v3.py        # (12 テスト)
│   ├── test_fixer_v3.py           # (13 テスト)
│   ├── test_guardian_v3.py        # (9 テスト)
│   ├── test_ags.py                # AGS ユニットテスト (17 テスト) - フェーズ 24
│   ├── test_ais.py                # AIS ユニットテスト (25 テスト) - フェーズ 25
│   ├── test_monitoring.py         # 監視ユニットテスト (15 テスト) - フェーズ 26
│   ├── test_mca_engine.py         # MCA エボリューションエンジン (18 テスト) - MS-4
│   ├── test_mca_professors.py     # MCA 教授 (21 テスト) - MS-4
│   ├── test_mca_proposals.py      # MCA 提案 (16 テスト) - MS-4
│   ├── test_notion_mca_client.py  # ✨ Notion MCA クライアント (40 テスト) - MS-7
│   ├── test_supabase_mca_mirror.py # ✨ Supabase ミラー (14 テスト) - MS-7
│   ├── test_notion_bridge.py      # ✨ Notion ブリッジ (21 テスト) - MS-7
│   ├── test_generic_markdown_translator.py  # ✨ ジェネリック Markdown (~12 テスト) - MS-8
│   ├── test_gguf_engine.py        # ✨ GGUF エンジン (~10 テスト) - MS-8
│   ├── test_a2a_protocol.py       # (5 テスト)
│   ├── test_execution.py          # (3 テスト)
│   ├── test_pipeline_e2e.py       # (4 テスト — faiss/numpy 互換性依存)
│   ├── contracts/                 # ✨ A2A イベント JSON v1 コントラクトテスト (修正 2026-02-28)
│   │   ├── test_handoff_packet.py
│   │   └── test_decision_contract.py
│   └── integration/               # フェーズ 23 統合テスト (41 テスト)
│       ├── test_a2a_handoff.py              # A2A パイプライン統合 (4 テスト)
│       ├── test_sentinel_v2_integration.py  # Sentinel 統合 (4 テスト)
│       ├── test_sherlock_v3_integration.py  # Sherlock 統合 (6 テスト)
│       ├── test_fixer_v3_integration.py     # Fixer 統合 (7 テスト)
│       ├── test_guardian_v3_integration.py  # Guardian 統合 (8 テスト)
│       ├── test_memory_recall.py            # メモリ統合 (5 テスト)
│       └── test_execution_verify.py         # 実行 & 検証統合 (7 テスト)
│
├── out/                            # 実行結果ディレクトリ
│   └── <event_id>/
│       ├── handoff_packet.json
│       ├── handoff_packet.attempt_N.json  # ✨ リトライ試行ファイル
│       ├── decision.json
│       ├── audit_report.json              # ✨ cgrf_metadata を含む
│       ├── verify_results.json            # ✨ 検証結果
│       └── execution_outcome.json
│
├── cgrf.py                         # ✨ 新規: CGRF CLI エントリーポイント
├── IMPLEMENTATION_SUMMARY_20260211.md  # ✨ 新規: 本日の成果の概要
└── README_merged_r2.md             # このファイル
```

---

## クイックスタート

### デモを実行する (すべてのイベント)

```bash
python demo/run_demo.py
```

**例の出力** (CGRF ティア表示付き):

```
✓ Sentinel V2: classification=incident, severity=medium
  [CGRF]: Tier 1 (Development) | Module: sentinel_v2 v2.1.0

✓ Sherlock V3: hypotheses=2, confidence=0.85, label=deps_missing
  [CGRF]: Tier 1 (Development) | Module: sherlock_v3 v3.0.0

✓ Fixer V3: fix_plan="Install missing dependencies...", risk=0.2
  [CGRF]: Tier 1 (Development) | Module: fixer_v3 v3.0.0

✓ Guardian V3: action=approve, risk_score=0.125
  [CGRF]: Tier 2 (Production) | Module: guardian_v3 v3.0.0

Pipeline completed in 78.4ms
```

### 自動実行と自動マージを有効にする

```bash
# ON/OFF スイッチ (config/settings.yaml)
auto_execution:
  enabled: true              # 自動実行 ON/OFF
  auto_merge:
    enabled: true            # 自動マージ ON/OFF
    max_risk_threshold: 0.25 # リスク閾値 (< 0.25 で自動マージ)
    ci_wait_timeout: 300     # CI 待機時間 (秒)
    merge_method: squash     # マージ方法 (squash/merge/rebase)
    exclude_branches:        # 除外するブランチ
      - main
      - master
      - production
    exclude_event_types:     # 除外するイベント
      - security_alert
      - deploy_failed

ワークフロー:

イベント → Guardian の判断 (リスク < 0.25)
              ↓
          PR 自動作成
              ↓
          CI 完了を待つ
              ↓
        CI 成功 → 自動マージ
```

詳細: docs/AUTO_EXECUTION.md

### 単一イベントを実行する

```bash
python demo/run_demo.py demo/events/ci_failed.sample.json
```

### Orchestrator V3 で実行する (リトライ検証有効)

```bash
python -m src.orchestrator_v3 demo/events/ci_failed.sample.json
```

### CGRF CLI で検証する

```bash
# 単一モジュールを検証
python cgrf.py validate --module src/agents/sentinel_v2.py --tier 1

# 複数モジュールをバッチ検証
python cgrf.py tier-check src/agents/*.py --tier 1

# すべてのモジュールのコンプライアンスレポート
python cgrf.py report --tier 1
```

詳細: [src/cgrf/README.md](src/cgrf/README.md)

### FastAPI サーバーを実行する```bash
uvicorn src.app:app --reload
```

### MCPサーバーを実行する（Claude Desktop / VS Code用）

```bash
python -m src.mcp_server.server
```

### MCA進化サイクルを実行する

```bash
# 基本的な実行（ドライラン）
python -m src.mca.cli evolve --meta config/mca_meta_001.yaml --dry-run

# メトリクス付き + 出力ファイルを指定
python -m src.mca.cli evolve --meta config/mca_meta_001.yaml \
  --files 120 --lines 15000 --tests 68 \
  --out out/mca_evolution.json --dry-run

# ロードマップIR統合（MS-5での完了が期待される）
python -m src.mca.cli evolve --roadmap-ir roadmap_ir.json --dry-run
```

AWS Bedrock接続のために`.env`に必要な環境変数は以下の通りです：

```bash
AWS_BEDROCK_ACCESS_KEY_ID=...
AWS_BEDROCK_SECRET_ACCESS_KEY=...
AWS_BEDROCK_REGION=us-east-1
```

### ロードマップ翻訳ツールを実行する

```bash
python -m src.roadmap_translator.cli translate \
  --in README.md EVOLUTION_ROADMAP.md IMPLEMENTATION_SUMMARY.md \
  --out roadmap_ir.json --report roadmap_ir.report.md
```

### テストを実行する

```bash
pytest tests/ -v
```

**テスト構成**：

- `test_pipeline_e2e.py` - 4つのE2Eテスト（ci_failed、security_alert、deploy_failure、verify_retry）
- `test_a2a_protocol.py` - 5つのA2Aプロトコルテスト
- `test_execution.py` - 3つの実行バックエンドテスト
- `test_sentinel_v2.py` - 9つのユニットテスト
- `test_sherlock_v3.py` - 12のユニットテスト
- `test_fixer_v3.py` - 13のユニットテスト
- `test_guardian_v3.py` - 9つのユニットテスト
- `test_ags.py` - 17のAGSユニットテスト（フェーズ24）
- `test_ais.py` - 25のAISユニットテスト（フェーズ25）
- `test_monitoring.py` - 15のモニタリングユニットテスト（フェーズ26）
- `test_cgrf_cli_json.py` - **8つのCGRF CLI JSONテスト** ✨ フェーズ27
- `tests/integration/` - 41の統合テスト（7ファイル）（フェーズ23）
- `test_mca_engine.py` - **18のMCAエンジンテスト** ✨ MS-4
- `test_mca_professors.py` - **21のMCA教授テスト** ✨ MS-4
- `test_mca_proposals.py` - **16のMCA提案テスト** ✨ MS-4
- `test_notion_mca_client.py` - **40のNotion MCAクライアントテスト** ✨ MS-7
- `test_supabase_mca_mirror.py` - **14のSupabaseミラーテスト** ✨ MS-7
- `test_notion_bridge.py` - **21のNotionブリッジテスト** ✨ MS-7
- `test_generic_markdown_translator.py` - **約12の一般的なMarkdownテスト** ✨ MS-8
- `test_gguf_engine.py` - **約10のGGUFエンジンテスト** ✨ MS-8
- `tests/contracts/` - A2AイベントJSON v1契約テスト（handoff_packetなど）
- Nemesis/Mike/F993などのサブシステムテスト
- **合計：1310件合格（2026-03-06時点のフルスイート、+177 VCC/OAD/Perplexity/Nemesisテスト）** ✅

> **CI条件**：リポジトリのルートから`pytest tests/ -q`で実行（ルートに`pytest.ini`が必要）。`test_pipeline_e2e.py`は`localhost:1234`（ローカルLLM）が利用できない場合、自動的にスキップされます — 実行中のモデルサーバーがない標準CIでは安全です。

### 環境変数（オプション、すべてのエージェントのAIを強化）

```bash
# Azure OpenAI（推奨）
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# またはOpenAIを直接
OPENAI_API_KEY=sk-...

# AWS Bedrock（MCA教授用）
AWS_BEDROCK_ACCESS_KEY_ID=...
AWS_BEDROCK_SECRET_ACCESS_KEY=...
AWS_BEDROCK_REGION=us-east-1

# GitHub実行（実際のPR作成用）
GITHUB_TOKEN=ghp_...
```

LLMキーが設定されている場合、すべての4つのエージェントは自然言語推論に基づいたAI駆動の分析を生成します。キーが存在しない場合、システムはルールベースのロジックにフォールバックします — 同じパイプライン、同じ契約、同じ出力。

---

## CGRF v3.0 ガバナンスフレームワーク ✨

**CGRF（完全ガバナンス＆リフレックスフレームワーク）**は、自律システムのための階層型ガバナンスフレームワークです。

### 階層システム

| 階層 | 名前               | テストカバレッジ | 実装時間 | 要件                         |
| ---- | ---------------- | -------- | ---- | -------------------------- |
| 0    | 実験的           | 0%       | <5分  | 基本構造のみ                     |
| 1    | 開発             | 50%目標    | ~2時間 | ドキュメンテーション、メタデータ、ユニットテスト |
| 2    | 生産             | 80%目標    | 1-2日 | 統合テスト、ポリシー遵守               |
| 3    | ミッションクリティカル | 95%目標    | ~1週間 | E2Eテスト、監査トレイル、完全なガバナンス        |

### CGRFメタデータ（すべてのエージェントに実装済み）

各エージェントはCGRF v3.0メタデータを出力します：

```python
@dataclass
class CGRFMetadata:
    report_id: str          # "SRS-SENTINEL-20260211-001-V3.0"
    tier: int               # 0-3
    module_version: str     # "2.1.0"
    module_name: str        # "sentinel_v2"
    execution_role: str     # "BACKEND_SERVICE"
    created: str            # ISOタイムスタンプ
    author: str             # "agent" | "human"
    last_updated: str       # ISOタイムスタンプ（オプション）
```

**現在の実装状況**（フェーズ23完了後）：

- Sentinel V2: **Tier 2（生産）** ✅
- Sherlock V3: **Tier 2（生産）** ✅
- Fixer V3: **Tier 2（生産）** ✅
- Guardian V3: **Tier 2（生産）** ✅

### CGRF CLIバリデーター

モジュールのCGRF準拠を検証するためのコマンドラインツール：

```bash
# 詳細な検証レポート
python cgrf.py validate --module src/agents/sentinel_v2.py --tier 1

# バッチ検証
python cgrf.py tier-check src/agents/*.py --tier 1

# 全体レポート
python cgrf.py report --tier 1
```

**検証項目**（Tier 1）：

- ✅ **parse**: Python ASTでパース可能
- ✅ **module_docstring**: モジュールのドキュメンテーション文字列が必要
- ✅ **cgrf_metadata**: 完全なメタデータ、Tier一致
- ✅ **test_file**: 対応するテストファイルが存在する

詳細：[src/cgrf/README.md](src/cgrf/README.md)

---

## REFLEX自己修復システム ✨

**REFLEX（5段階パイプライン）**: 観察 → 診断 → 反応 → 検証 → 学習

### Orchestrator V3の検証再試行機能

`src/orchestrator_v3.py`は、検証失敗時に自動的に再試行します：

```python
# 最大2回の試行、検証失敗時に自動再試行
max_attempts = 2
attempt_no = 1

while attempt_no <= max_attempts:
    # パイプラインを実行
    run_pipeline()

    # 検証結果を確認
    verify_results = read_verify_results()

    if verify_results["all_success"]:
        break  # 成功 → 完了

    if attempt_no < max_attempts:
        # フィードバックを注入して再試行
        inject_verify_feedback()
        attempt_no += 1
        continue

    # 最終試行が失敗 → 終了
    break
```

**生成されたファイル**：

- `out/<event_id>/handoff_packet.attempt_1.json` - 試行1の結果
- `out/<event_id>/audit_report.attempt_1.json` - 試行1の監査
- `out/<event_id>/decision.attempt_1.json` - 試行1の決定
- `out/<event_id>/verify_results.json` - 検証結果（all_successフラグ）
- `out/<event_id>/handoff_packet.json` - 最終結果（packet_artifacts.attempts配列）

**E2Eテスト**：

```bash
pytest tests/test_pipeline_e2e.py::test_verify_retry_on_failure -v
```

---

## デモ出力

デモは3つのイベントをフルV3パイプラインを通じて実行します：

### 検証ステップ（verification_steps）

Fixer V3は、Sherlockのラベルに基づいて修正後の検証コマンドを提案します（例：`deps_missing` / `permission_denied` / `security_alert`）：

**deps_missing**：

```bash
python -c "import sys; print(sys.version)"
pip install -r requirements.txt
python -c "import {module}"
```

**permission_denied**：

```bash
ls -l {file}
test -r {file} && echo OK_READ || echo NG_READ
test -x {file} && echo OK_EXEC || echo NG_EXEC
```

**security_alert**：

```bash
npm ls {package} || true
npm audit || true
npm audit fix || true
npm ls {package} || true
```

### Guardianによるリスク軽減

Guardian V3は、検証ステップの存在に基づいてリスクを調整します：

```
base_risk = (fixer_risk * 0.4) + (severity_weight * 0.3) + confidence_penalty + security_bump

mitigations:
  - verification_steps provided: -0.04
  - verification all success: -0.08

final_risk = base_risk - mitigations
```

**監査出力**（`audit_report.json`）：

```json
{
  "artifacts": {
    "guardian_risk_model": {
      "base_risk": 0.285,
      "mitigations": [
        {"id": "M_VERIFICATION_STEPS_PROVIDED", "delta": -0.04, "active": true},
        {"id": "M_VERIFICATION_PASSED", "delta": -0.08, "active": false}
      ],
      "final_risk": 0.245,
      "verify": {
        "has_steps": true,
        "has_results": false,
        "all_success": false
      }
    }
  },
  "cgrf_metadata": {
    "sentinel": {"tier": 1, "module_name": "sentinel_v2", ...},
    "sherlock": {"tier": 1, "module_name": "sherlock_v3", ...},
    "fixer": {"tier": 1, "module_name": "fixer_v3", ...},
    "guardian": {"tier": 2, "module_name": "guardian_v3", ...}
  }
}
```

### デモ結果の概要

| イベント            | 深刻度 | 自信  | リスクスコア | 決定            | CGRF Tier   |
| --------------- | --- | ---- | ------ | ------------- | ----------- |
| CI失敗（依存関係の欠如）   | 中程度 | 0.85 | 0.125  | **承認**（自動）    | Tier 1 x 3  |
| デプロイ失敗（権限）      | 高   | 0.90 | 0.198  | **承認**（自動）    | Tier 1 x 3  |
| セキュリティアラート（CVE） | 重大  | 0.90 | 0.608  | **承認が必要**（人間） | + Tier 2 x1 |

---

## モジュールの理論

各フォルダーはパイプライン内の単一の責任を分離します。システムは、すべてのモジュールが外部依存関係なしに実行できるように設計されています（ローカルファイルベースのバックエンド）またはAzure管理サービスに切り替えることができます — 同じコードパス、同じ契約、異なるバックエンド。

### 主要モジュールの詳細

**`config/`** — 外部サービスのための設定テンプレート。設定は環境固有であり、アプリケーションロジックではないため、`src/`の外に保持されています。`azure.yaml.example`は、システムが接続できるAzureサービスと各サービスが必要とする資格情報のドキュメントとして機能します。

**`demo/`** — 自己完結型のデモハーネス。`events/`サブフォルダーには、異なるパイプラインの動作を実行するためのキュレーションされたJSONペイロードが含まれています。`run_demo.py`はすべてのコマンドを順次実行し、色付きのターミナル出力を提供します（CGRF Tier表示付き）。

**`src/types.py`** — すべてのデータ契約の唯一の真実のソース。`EventJsonV1`、`HandoffPacket`、`AgentOutput`、`Decision`、および**`CGRFMetadata`**（v3.0）を定義します。システム内のすべてのモジュールはここからインポートします。

**`src/orchestrator_v3.py`** — A2A + メモリ + 実行 + リフレックス + **検証再試行**。`out/<event_id>/verify_results.json`を読み取り、検証失敗時に最大2回再試行します。各試行のファイルを保存し、最終結果に試行配列を含めます。

**`src/app.py`** — パイプラインをHTTP経由で公開するFastAPIアプリケーション。GitHub ActionsおよびAzure Alerts用のWebhookエンドポイント、生のイベント送信エンドポイント、パイプラインのステータスクエリ、エージェントレジストリ、監査トレイルの取得、リフレックスルールのリスト、SSEストリーミングを提供します。

**`src/agents/`** — 診断修復パイプラインを形成する4つの専門エージェント。各エージェントは**CGRF v3.0メタデータ**を出力します：

1. **Sentinel V2**（Tier 1） — 初動対応者。イベントタイプを分類し、深刻度を割り当て、ログテキストから信号を抽出します。
2. **Sherlock V3**（Tier 1） — 根本原因分析者。仮説を生成し、証拠の強さに基づいて自信をスコアリングし、過去のインシデントからのメモリを取り入れます。
3. **Fixer V3**（Tier 1） — 修復エンジニア。修正計画を提案し、リスクを見積もり、**verification_steps**を生成します。
4. **Guardian V3**（Tier 2） — ガバナンスゲート。多因子リスクスコアを計算し、RAIポリシーおよびガバナンスルールに対して検証し、決定を下します。

各エージェントは2つのモードで動作します：

- **LLMモード**: Azure OpenAI / OpenAIによる自然言語分析
- **ルールモード**: パターンマッチングとテンプレート

**`src/ags/`** ✨ — **AGS（エージェントガバナンスシステム）パイプライン**（フェーズ24）。Guardianの決定後に実行前に挿入される「憲法的司法」層。4段階のパイプライン（S00 GENERATOR → S01 DEFINER → S02 FATE → S03 ARCHIVIST）を通じて二重チェックガバナンスを実現します：

- `caps_stub.py` - CAPSグレーディングシステム（D/C/B/A/S） + `get_ais_profile()` AISブリッジ
- `s00_generator.py` - HandoffPacket + Decision → SapientPacket変換
- `s01_definer.py` - スキーマ検証 + CAPS Tier要件チェック
- `s02_fate.py` - 5つのポリシーゲート → ALLOW/REVIEW/DENYの決定
- `s03_archivist.py` - 監査ハッシュチェーン記録
- `pipeline.py` - AGSPipelineランナー、AGSVerdictデータクラス
- 設計原則：エスカレーションのみ（厳格にすることはできるが、緩和することはできない）、フェイルオープン（可用性を優先）**`src/ais/`** ✨ — **AIS (エージェントインテリジェンスシステム) XP/TP経済** (フェーズ25)。XP/TPのデュアルトークン経済におけるエージェントの能力を動的に管理します：

- `profile.py` - AgentProfileデータクラス（XP/TPトラッキング、トランザクションログ、CAPSグレードの自動解決）
- `storage.py` - ProfileStore（ファイルベースのJSON永続化、`data/ais/profiles/{agent_id}.json`）
- `costs.py` - CostTable（アクションごとのTPコスト：approve_fix=50、create_pr=70、deploy=90）
- `rewards.py` - RewardCalculator（ティア乗数、品質ボーナス+50%、クリティカルTP、低リスクボーナス）
- `engine.py` - AISEngine（予算チェック、報酬記録、TP支出、フェイルオープン）
- 設計原則：フェイルオープン（エラー時にCAPSスタブデフォルトにフォールバック）、エージェントごとのトラッキング

**`src/monitoring/`** ✨ — **モニタリング & 可観測性** (フェーズ26/MS-7)。Prometheusメトリクス出力とGrafanaダッシュボード統合：

- `metrics.py` - 16のPrometheusメトリクス定義（12 DevOps + 4 MCA）、孤立したCollectorRegistry、フェイルオープン記録関数
  - MS-7の追加：`citadel_mca_evolution_proposals_total`、`citadel_mca_evolution_proposals_approved`、`citadel_mca_domain_health_score`、`citadel_mca_evolution_cycle_duration_seconds`
- `middleware.py` - オプションのFastAPI HTTPミドルウェア（`citadel_http_request_duration_seconds`）
- `/metrics`エンドポイントでのPrometheusスクレイピングをサポート
- 設計原則：フェイルオープン（`prometheus_client`がインストールされていなくてもすべての機能が動作）、孤立したレジストリ（テスト安全）

**`grafana/`** ✨ — **Grafanaダッシュボード** (フェーズ26)。Prometheusメトリクスを視覚化するためのJSONプロビジョニング：

- `citadel_dashboard.json` - 4つのセクションにわたる11のパネル（パイプライン概要、エージェントアクティビティ、ガバナンス、自動マージ）
- パイプライン実行率、進行中のゲージ、レイテンシパーセンタイル、エージェント呼び出し、XP/TP/グレード、AGS判定、リスク分布

**`src/cgrf/`** ✨ — **CGRF v3.0 CLIバリデーター**。モジュールのCGRFティア準拠を検証するためのコマンドラインツール：

- `cli.py` - 3つのコマンド（validate、tier-check、report）
- `validator.py` - ティア0-3の検証ロジック
- ティア要件チェック：parse、docstring、cgrf_metadata、test_file、integration_tests、e2e_tests
- カラーコード出力（ティア0=DIM、1=CYAN、2=YELLOW、3=RED）
- Windowsコンソールサポート

**`src/a2a/`** — エージェント間のハンドオフプロトコル。エージェントの登録、能力の発見、メッセージのルーティング、実行トレースを処理するプロトコルレイヤーを通じて`A2AMessage`オブジェクトをディスパッチします。

**`src/llm/`** — LLM抽象化レイヤー。`client.py`は、マルチバックエンドフォールバックチェーンを持つ`LLMClient`を実装します：Azure OpenAI → OpenAI直接 → 優雅な失敗（エージェントはルールにフォールバック）。

**`src/memory/`** — パイプライン実行を通じて学習するためのインシデントメモリ。`store_v2.py`は`recall(query, k)`と`remember(event_id, summary, tags, outcome)`を提供します。オーケストレーターはSherlockが実行される前にメモリを呼び出します。

**`src/execution/`** — 「ループを閉じる」レイヤー。`runner_V2.py`はバックエンド戦略パターンを実装します：

- `DryRunExecutionBackend` - アクションをログします（デモ/テスト）
- `LocalExecutionBackend` - JSONアーティファクトをディスクに書き込みます
- `GitHubExecutionBackend` - 実際のブランチを作成し、PRを開きます

**`runner_V2.py`は`verify_results.json`を生成します**（検証ステップの実行結果、`all_success`フラグ）：

```json
{
  "schema_version": "verify_results_v0",
  "event_id": "demo-ci-failed-001",
  "results": [
    {"step": "python -c 'import sys'", "success": true, "output": "3.11.0"},
    {"step": "pip install -r requirements.txt", "success": true, "simulated": true}
  ],
  "all_success": true,
  "simulated": true
}
```

**`src/audit/`** — 改ざん防止監査トレイル。`report.py`は**CGRFメタデータ**を含む監査報告JSONを生成します。`logger.py`はSHA-256ハッシュチェーン監査ロガーを実装します。

**`src/approval/`** — ヒューマンインザループ承認ワークフロー。Guardianが`need_approval`を返すと、オーケストレーターはこのモジュールを使用して実行が進む前に人間のレビューを要求します。**`src/governance/`** — 責任あるAIポリシーフレームワーク。`policies.yaml`は6つのRAI原則、5つのガバナンスルール、3つのコンプライアンスマッピングを宣言します。`policy_engine.py`はランタイムでエンジンをロードします。

**`src/reflex/`** — 決定後の自動化ルール。`manifest.yaml`は、イベントタイプ、重大度、リスクスコアに基づいてGuardianの決定後にトリガーされるルールを宣言します。`dispatcher.py`はマニフェストを読み取り、現在のイベント/決定に対してルールを照合します。

**`src/ingest/`** — イベントの取り込みと正規化。`normalizer.py`は異なるソースからのペイロードを標準の`EventJsonV1`形式に変換します。`outbox.py`はファイルベースのアウトボックスパターンを実装します。

**`src/github/`** — 実行のためのGitHub REST API統合。ブランチの作成、ファイルのコミット、プルリクエストのオープン、ワークフローログの取得、失敗したCIワークフローの再トリガー、Webhook署名の検証を処理します。

**`src/streaming/`** — サーバー送信イベントを介したリアルタイムパイプライン観察。`emitter.py`は、任意のSSEクライアントがリアルタイムで消費できるイベントを発信します。

**`src/mcp_server/`** — モデルコンテキストプロトコルサーバー。`server.py`はパイプラインを6つのツールと2つのリソースとして公開し、MCP互換のクライアント（Claude Desktop、VS Code with Copilotなど）から呼び出すことができます。

**`src/dashboard/`** — ウェブベースのコントロールパネル。イベント提出フォーム、パイプラインステージの進捗の視覚化、エージェント出力カード、リスクゲージ、監査トレイル表示、メモリパネル、エージェントレジストリを提供します。

**`src/azure/`** — Azureサービスバックエンド。各ファイルはローカルバックエンドと同じABC/インターフェースを実装していますが、Azureサービスによってバックアップされています。

**`src/roadmap_ir/`** ✨ — **ロードマップIRスキーマ** (MS-1)。システム全体の共通契約（JSONスキーマドラフト2020-12 + Pydantic v2）：

- `schema.json` - JSONスキーマ定義（Source、Catalog、Item、Evidence、Conflict、Note、Metrics）
- `types.py` - Pydantic v2モデル（7つの列挙型、16のモデル、Evidenceユニオン）
- `validators.py` - セマンティックバリデーション（IDの重複を禁止、証拠のないアイテムに対してstatus=unknownを強制、サイクル検出）
- 31のテスト、CGRFティア1

**`src/roadmap_translator/`** ✨ — **ロードマップトランスレーター** (MS-2)。決定論的（非LLM）文書→IR変換パイプライン：

- `pipeline.py` - 7ステップのオーケストレーション：Ingest→Detect→Translate→Normalize→Merge→Validate→Emit
- `translators/readme.py` - README `**最新の実装**` → アイテム抽出
- `translators/markdown_roadmap.py` - RoadMap `### フェーズN:` → アイテム抽出
- `translators/implementation_summary.py` - 実装サマリー `### N. タイトル ✅` → アイテム抽出
- `cli.py` - `translate --in ... --out roadmap_ir.json --report roadmap_ir.report.md`
- 37のテスト、すべての12モジュールCGRFティア1

**`src/mca/`** ✨ — **MCA進化エンジン** (MS-4)。AI教授による自動進化サイクル：

- `evolution_engine.py` - 7フェーズのオーケストレーション（Data→Meta→Metrics→AI→Proposals→SANCTUM→Publisher）
- `metrics_aggregator.py` - コード/計画/フェーズ/IRメトリクスの統合スナップショット
- `professors/bedrock_adapter.py` - `BedrockProfessorBase`ミキシン（AWS Bedrock経由のClaude Opus 4.5）
- `professors/prof_mirror.py` - ミラープロフェッサー：コードパターン + 計画カバレッジ分析
- `professors/prof_oracle.py` - オラクルプロフェッサー：戦略的ガイダンス + 健康評価 + ティアカバレッジ
- `professors/prof_government.py` - ガバメントプロフェッサー：CAPS準拠 + 提案の承認/拒否 + enum_tags
- `proposals/models.py` - `EvolutionProposal`（EP-CODE/EP-RAG/EP-SALES/EP-STALE/EP-GAP） + 5つのファクトリ関数
- `cli.py` - `evolve --meta ... --roadmap-ir ... --out ... --dry-run`
- 55のテスト、すべての9モジュールCGRFティア1
- 設計原則：教授は`BedrockProfessorBase`ミキシンでProfessorBaseを拡張します（元のOpenAIパスを保持）

**`src/infra/`** ✨ — **インフラストラクチャ** (MS-4/MS-7)。外部サービスクライアント：

- `bedrock_professor_client.py` - AWS Bedrock Claude呼び出し（boto3、リトライ、`load_dotenv()`サポート）
- 環境変数：`AWS_BEDROCK_ACCESS_KEY_ID`、`AWS_BEDROCK_SECRET_ACCESS_KEY`、`AWS_BEDROCK_REGION`
- `notion_mca_client.py` ✨ - Notion APIクライアント（MS-7）：EVO Trackerページへのブロック追加、ZES RAG DBへの記録登録、直接リクエスト
- `supabase_mca_mirror.py` ✨ - Supabase RESTミラー（MS-7）：`automation_events` + `mca_proposals`テーブル、supabase-pyに依存しない直接REST呼び出し
- 環境変数（MS-7）：`NOTION_TOKEN`、`NOTION_EVO_TRACKER_PAGE_ID`、`NOTION_ZES_RAG_DB_ID`、`SUPABASE_URL`、`SUPABASE_SERVICE_KEY`
- 設計原則：資格情報が設定されていない場合は優雅なノーオプ、`dry_run=True`でテスト可能

**`src/mca/notion_bridge.py`** ✨ — **Notion/Supabaseブリッジ** (MS-7)。MCA提案をNotion + Supabaseに同期するためのブリッジレイヤー：

- `publish_proposal()` - EvolutionProposal → Notion EVO Tracker + ZES RAG DB + Supabase三点同期
- 40 + 14 + 21 = **75のテスト**（test_notion_mca_client / test_supabase_mca_mirror / test_notion_bridge）
- 4つのMCA Prometheusメトリクスが追加されました：`citadel_mca_evolution_proposals_total`、`citadel_mca_evolution_proposals_approved`、`citadel_mca_domain_health_score`、`citadel_mca_evolution_cycle_duration_seconds`

**`src/roadmap/gguf_engine.py`** ✨ — **GGUFローカル推論エンジン** (MS-8)。`llama_cpp`がインストールされていない場合は自動的にルールベースにフォールバックします：

- `load_model()` - `CITADEL_GGUF_MODEL`環境変数からモデルをロードし、失敗時には`None`を返します
- `generate_text(prompt)` - モデルあり：`Llama.create_completion()`、モデルなし：ルールベース
- `summarize(text)` - 最初の150文字にトリムします
- `generate_risk(text)` - "blocked"/"dependency"/"not implemented"キーワードからリスク文字列を生成します
- `recommend(status, verify)` - ステータス/検証の組み合わせからテンプレートを生成します

**`src/roadmap_translator/enricher.py`** ✨ — **IRエンリッチャー** (MS-8)。各ロードマップIRのアイテムをGGUFで自動的にエンリッチします：

- `enrich_ir(ir, engine)` - `raw`に`summary`、`recommendations`、`risk_notes`を追加します
- エンジンが指定されていない場合は自動的に`gguf_engine.load_model()`を呼び出します

**`src/roadmap_translator/translators/generic_markdown.py`** ✨ — **汎用Markdownトランスレーター** (MS-8)。他のトランスレーターによって一致しない`.md`ファイルのフォールバック：

- 見出し（H1からH6）+ 番号付き/箇条書きリストからアイテムを抽出します
- ステータス検出：`✅`→完了、`TODO/[ ]/planned`→計画中、`blocked/🚫`→ブロック、`WIP/in_progress`→進行中、その他→不明
- `raw.hierarchy_path`に親見出しの階層を保持します
- item_id: `generic-{slug}`

**`src/roadmap_translator/translators/gitlog.py`** ✨ — **Gitlogトランスレーター** (MS-8)。`git log`テキスト出力から`EvidenceGit`を持つアイテムを生成します：

- 入力：`git log --pretty=format:"%H%n%an%n%ai%n%s" --name-only`の出力
- `FILE_PHASE_MAP`：ファイルパターンをフェーズ番号にマッピングするフォールバック推定辞書
- item_id: `git-{commit[:7]}`

**`ci/translate_evolve_publish.sh`** ✨ — **CIバルクスクリプト** (MS-8)。GitHub Actions / GitLab CI互換のスクリプトで、translate → evolve → publishを行います：

- 環境変数をサポート：`CITADEL_DRY_RUN`、`CITADEL_GGUF_MODEL`、`NOTION_TOKEN`、`SUPABASE_URL`
- エラー時にコード1で終了します

**`src/contracts/`** ✨ — **A2AイベントJSON v1契約** (改訂2026-02-28)。型安全なA2Aハンドオフ契約：

- `handoff_packet.py` - `source_agent_id`/`target_agent_id`/`payload`フィールド、jsonschema構造検証、`from_dict()`で`jsonschema.ValidationError`を発生させます
- `handoff_packet_contract.py` - `id`/`timestamp`/`payload`フィールド、`__post_init__`で`ValueError("Missing required fields: [...]")`を発生させ、`to_json()` / `from_json()`をサポートします
- `decision_contract.py` - ISO 8601の'T'区切りを強制（空白区切りを明示的に拒否）

**`vscode-extension/`** ✨ — **VS Code拡張機能** (フェーズ27)。CGRFティアのリアルタイムIDEバリデーション：

- `citadel-cgrf/src/extension.ts` - エントリーポイント（コマンド登録、onSave、エディタ変更ハンドラ）
- `citadel-cgrf/src/cgrfRunner.ts` - `python cgrf.py validate --json`サブプロセス + JSONパース
- `citadel-cgrf/src/statusBar.ts` - ステータスバーのティア表示（準拠=緑、エラー=赤）
- `citadel-cgrf/src/diagnostics.ts` - CGRFバリデーション失敗 → VS Codeの問題パネル
- `citadel-cgrf/src/codeLens.ts` - `_CGRF_TIER = N`定義行のティアバッジCodeLens
- `citadel-cgrf/src/config.ts` - 拡張設定管理**`tests/`** — 自動検証。1310のテストが合格しました（2026-03-06現在）：

- `test_pipeline_e2e.py` - 4つのE2Eテスト
- `test_a2a_protocol.py` - 5つのA2Aテスト
- `test_execution.py` - 3つの実行テスト
- `test_sentinel_v2.py` - 9つの単体テスト
- `test_sherlock_v3.py` - 12の単体テスト
- `test_fixer_v3.py` - 13の単体テスト
- `test_guardian_v3.py` - 9つの単体テスト
- `test_ags.py` - 17のAGS単体テスト（フェーズ24 + 1つのAIS統合テスト）
- `test_ais.py` - 25のAIS単体テスト（フェーズ25）
- `test_monitoring.py` - 15のモニタリング単体テスト（フェーズ26）
- `test_cgrf_cli_json.py` - 8つのCGRF CLI JSONテスト ✨ フェーズ27
- `test_mca_engine.py` - 18のMCA進化エンジンテスト ✨ MS-4
- `test_mca_professors.py` - 21のMCA教授テスト ✨ MS-4
- `test_mca_proposals.py` - 16のMCA提案テスト ✨ MS-4
- `test_notion_mca_client.py` - 40のNotion MCAクライアントテスト ✨ MS-7
- `test_supabase_mca_mirror.py` - 14のSupabaseミラーテスト ✨ MS-7
- `test_notion_bridge.py` - 21のNotionブリッジテスト ✨ MS-7
- `test_generic_markdown_translator.py` - 約12の一般的なMarkdownテスト ✨ MS-8
- `test_gguf_engine.py` - 約10のGGUFエンジンテスト ✨ MS-8
- `tests/contracts/` - A2AイベントJSON v1契約テスト ✨ （改訂2026-02-28）
- `tests/integration/` - 41の統合テスト（7ファイル）（フェーズ23）
- Nemesis/Mike/F993などのサブシステムテスト。

---

## LLM駆動のデュアルモードエージェント

すべてのV3エージェントは同じパターンに従います：**最初にLLMを試し、ルールにフォールバック**。

```
リクエスト → LLMClient.complete(system_prompt, context)
              │
         ┌────┴────┐
         │ 成功      │ → 構造化されたJSON（AI生成）+ cgrf_metadataを返す
         └────┬────┘
              │ 失敗 / APIキーなし
              ▼
         ルールベースのロジック → 構造化されたJSON（テンプレートベース）+ cgrf_metadataを返す
```

### LLMバックエンドチェーン

```
DevOpsエージェント:
  Azure OpenAI (AZURE_OPENAI_ENDPOINT)
      ↓ 利用不可
  OpenAI Direct (OPENAI_API_KEY)
      ↓ 利用不可
  ルールベースのフォールバック（外部依存なし）

MCA教授:
  AWS Bedrock (Claude Opus 4.5)
      ↓ 利用不可
  Noneを返す → EvolutionEngineがスキップされる
```

各エージェントには、構造化されたJSON出力スキーマを持つ専用のシステムプロンプトがあります：

- **Sentinel**: インシデントの検出、分類、優先順位付け + CGRFメタデータ（Tier 1）
- **Sherlock**: 根本原因の推論と仮説生成、信頼度スコア、証拠チェーン + CGRFメタデータ（Tier 1）
- **Fixer**: 修正計画、リスク評価、ロールバック戦略、パッチ生成、**verification_steps** + CGRFメタデータ（Tier 1）
- **Guardian**: ガバナンスの決定、ポリシー遵守、RAI評価、**guardian_risk_model** + CGRFメタデータ（Tier 2）

すべての応答には、AIがアクティブな場合に`llm_powered: true/false`と`llm_usage`メトリクスが含まれます。

---

## MCPサーバー（モデルコンテキストプロトコル）

MCP互換クライアント（Claude Desktop、VS Codeなど）用のツールとしてパイプラインを公開します。

### ツール

| ツール                        | 説明                                |
| -------------------------- | --------------------------------- |
| `citadel_run_pipeline`     | イベントに対してフルパイプラインを実行します               |
| `citadel_diagnose`         | イベントの説明に対してSentinel + Sherlockを実行します |
| `citadel_propose_fix`      | 診断に対してFixerを実行します                    |
| `citadel_check_governance` | 修正提案に対してGuardianを実行します               |
| `citadel_recall_memory`    | インシデントメモリを検索します                      |
| `citadel_audit_trail`      | イベントの監査チェーンを取得します                    |

### リソース

| URI                  | 説明                   |
| -------------------- | -------------------- |
| `citadel://agents`   | 登録されたエージェントとその機能のリスト |
| `citadel://policies` | ガバナンスポリシーと遵守マッピング    |

### Claude Desktop構成

```json
{
  "mcpServers": {
    "citadel-lite": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/path/to/citadel_lite"
    }
  }
}
```

---

## ウェブダッシュボード

リアルタイムのシングルページダッシュボードは`src/dashboard/index.html`にあります：

- **イベント提出フォーム** — ブラウザからパイプラインをトリガーします
- **パイプラインの進行状況** — ステージのライブ追跡（Sentinel → Sherlock → Fixer → Guardian → 実行）
- **エージェント出力カード** — 各エージェントからの展開可能なJSON結果 + **CGRFメタデータ**
- **ガバナンスパネル** — リスクゲージ、決定表示、ポリシー参照、**guardian_risk_model**
- **監査トレイル** — 整合性ステータスを持つハッシュチェーンの視覚化
- **メモリパネル** — 再呼び出されたインシデントと類似スコア
- **エージェントレジストリ** — 登録されたすべてのA2Aエージェントとその機能

ダークテーマを特徴とし、リアルタイム更新のためにSSEで接続されており、ポーリングフォールバックがあります。

---

## SSEパイプラインストリーミング

リアルタイムのサーバー送信イベントストリーミングを通じたライブパイプライン観察：

```
GET /stream/{event_id}  →  SSEストリームのPipelineEventメッセージ
```

イベントタイプ：`stage_start`、`stage_complete`、`agent_output`、`decision`、`error`、`pipeline_complete`

ウェブダッシュボードによって使用され、任意のSSE互換クライアントで利用可能です。

---

## GitHub統合

`src/github/client.py`は実際のGitHub実行を提供します：

- **Fix PRの作成** — ブランチの作成、ファイルのコミット、PRのオープン（エンドツーエンド）
- **ワークフローログ** — 診断のためのCI/CD実行ログの取得
- **ワークフローの再実行** — 修正後の失敗したCIの再トリガー
- **Webhook検証** — HMAC-SHA256署名の検証

`GITHUB_TOKEN`と`EXECUTION_MODE=github`を設定して、ライブPR作成を有効にします。

---

## アーキテクチャ

### パイプラインフロー（CGRF v3.0統合）
```
外部イベント → 正規化 → アウトボックス → オーケストレーターV3
                                            │
                    ┌───────────────────────┤
                    ▼                       ▼
              メモリリコール              A2Aプロトコル
                    │                      │
                    ▼                      ▼
              ┌─────────┐  ┌─────────┐  ┌───────┐  ┌──────────┐
              │Sentinel │→│ Sherlock │→│ Fixer  │→│ Guardian  │
              │ 検出 & │  │診断 │  │提案 │  │ガバナンス│
              │分類 │  │Tier 1   │  │Tier 1 │  │  Tier 2  │
              └─────────┘  └─────────┘  └───────┘  └──────────┘
                   ↓             ↓           ↓           ↓
              CGRFメタ    CGRFメタ   CGRFメタ   CGRFメタ
                                                         │
                                                    Guardian Decision
                                                         │
                                                         ▼
                                                ┌──────────────┐
                                                │  AGSパイプライン │ ✨ フェーズ24
                                                │  S00→S01→S02  │
                                                │  →S03         │
                                                │ エスカレーション    │
                                                │  専用チェック │
                                                └──────┬───────┘
                                                       │
                              ┌─────────────────────────┤
                              ▼              ▼           ▼
                          承認       承認が必要      ブロック
                              │              │           │
                              ▼              ▼           ▼
                     反射的ディスパッチ   人間のゲート    停止 + レポート
                              │              │
                              ▼              ▼
                         実行          実行
                         (PR/CI)      (承認された場合)
                              │
                              ▼
                    ExecutionRunner (runner_V2.py)
                              │
                              ▼
                    verify_results.json生成
                              │
                              ▼
                    ┌─────────┴─────────┐
                    ▼                   ▼
              all_success=true    all_success=false
                    │                   │
                    ▼                   ▼
                  完了            retry < max_attempts?
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                            はい                 いいえ
                              │                   │
                Inject verify_feedback          完了
                              │              (失敗)
                         attempt += 1
                              │
                              └─→ パイプラインを再実行
```

### REFLEX 5段階パイプライン

```
1. 観察   → ExecutionRunnerがverification_stepsを実行
2. 診断  → verify_results.json生成、all_successの決定
3. 応答   → オーケストレーターV3が再試行の決定を行う
4. 検証    → 次の試行で再実行し、verify_feedbackを注入
5. 学習     → メモリストアに成功/失敗パターンを保存
```

### A2Aハンドオフプロトコル

エージェントは、共有の`HandoffPacket`を含む`A2AMessage`オブジェクトを介して通信します。各エージェントは：

1. `handoff()`を介してパケットを受け取ります
2. `packet.agent_outputs`から上流の出力を読み取ります
3. `packet.memory_hits`からメモリヒットを読み取ります
4. `packet.add_output()`を介して独自の出力 + **cgrf_metadata**を追加します
5. 更新されたメッセージを返します

### Guardian V3 — マルチファクタリスクスコアリング

```python
# 基本リスク計算
base_risk = (fixer_risk * 0.4) + (severity_weight * 0.3) + confidence_penalty + security_bump

# 深刻度の重み
severity_weight: low=0.1, medium=0.3, high=0.6, critical=0.9

# 信頼度ペナルティ
confidence_penalty: (1 - sherlock_confidence) * 0.2

# セキュリティバンプ
security_bump: +0.2 if "security_vulnerability" in signals else 0.0

# 緩和策
mitigation_verification_steps = -0.04 if has_verification_steps else 0.0
mitigation_verification_passed = -0.08 if verification_all_success else 0.0

# 最終リスク
aggregate_risk = base_risk + mitigation_verification_steps + mitigation_verification_passed
aggregate_risk = max(0.0, min(1.0, aggregate_risk))

# 決定バンド
if aggregate_risk < 0.25:
    action = "approve"
elif aggregate_risk < 0.65:
    action = "need_approval"
else:
    action = "block"
```

**監査出力** (`guardian_risk_model`):

```json
{
  "base_risk": 0.285,
  "mitigations": [
    {"id": "M_VERIFICATION_STEPS_PROVIDED", "delta": -0.04, "active": true},
    {"id": "M_VERIFICATION_PASSED", "delta": -0.08, "active": false}
  ],
  "final_risk": 0.245,
  "verify": {
    "has_steps": true,
    "has_results": false,
    "all_success": false
  }
}
```

### 責任あるAIフレームワーク

6つのRAI原則（RAI-001からRAI-006）：

- 人間の監視、透明性、監査トレイルの整合性
- 比例的応答、安全策のデフォルト、メモリプライバシー

5つのガバナンスルール（リスク閾値 + セキュリティ + 生産保護）

3つのコンプライアンスマッピング：Microsoft RAI基準、SOC 2 Type II、ISO 27001

### 監査トレイル

各パイプライン実行はSHA-256ハッシュチェーンを生成します：

```
genesis → event_received → sentinel → sherlock → fixer → guardian → ags.verdict → execution → ais.rewards → completion
```

各エントリは次のようにハッシュ化されます：`SHA256(previous_hash + stage + timestamp + payload)`

監査報告には**cgrf_metadata**セクションが含まれます：

```json
{
  "cgrf_metadata": {
    "sentinel": {
      "report_id": "SRS-SENTINEL-20260211-abc123-V2.1.0",
      "tier": 1,
      "module_version": "2.1.0",
      "module_name": "sentinel_v2",
      "execution_role": "BACKEND_SERVICE",
      "created": "2026-02-11T12:34:56Z",
      "author": "agent"
    },
    "sherlock": {...},
    "fixer": {...},
    "guardian": {...}
  }
}
```

---

## Azure統合（オプション）

環境変数を設定するか、`config/azure.yaml.example`を`config/azure.yaml`にコピーします：| サービス                  | 目的            | 環境変数                                    |
| --------------------- | ------------- | --------------------------------------- |
| Service Bus           | イベントキュー       | `AZURE_SERVICEBUS_CONNECTION`           |
| Cosmos DB             | インシデントメモリ     | `AZURE_COSMOS_CONNECTION`               |
| Azure OpenAI          | エージェント用LLM    | `AZURE_OPENAI_ENDPOINT`                 |
| Foundry Agent Service | エージェントホスティング  | `AZURE_FOUNDRY_ENDPOINT`                |
| Application Insights  | テレメトリー         | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| Azure Storage         | アーティファクトストレージ | `AZURE_STORAGE_CONNECTION`              |

Azureが構成されていない場合、システムは完全にローカルでファイルベースのバックエンドで実行されます。同じコードパス、同じ契約、異なるバックエンド。

---

## API エンドポイント (FastAPI)

| メソッド | パス                     | 説明                              |
| ---- | ---------------------- | ------------------------------- |
| POST | `/webhook/github`      | GitHub Actions webhook            |
| POST | `/webhook/azure`       | Azure Alert webhook               |
| POST | `/webhook/event`       | 生の EventJsonV1 提出                 |
| GET  | `/pipeline/{event_id}` | パイプラインのステータス + 出力               |
| GET  | `/stream/{event_id}`   | SSE リアルタイムパイプラインストリーム            |
| GET  | `/agents`              | エージェントレジストリ (カード + 機能)           |
| GET  | `/audit/{event_id}`    | イベント監査トレイル                       |
| GET  | `/reflex/rules`        | アクティブなリフレックスルールマニフェスト           |
| GET  | `/metrics`             | Prometheus メトリクス出力 ✨ フェーズ 26   |
| GET  | `/health`              | ヘルスチェック (monitoring_enabled を含む) |

---

## ハッカソンカテゴリカバレッジ

| カテゴリ                             | 主な機能                                                                                                                                                                                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **グランプリ: エージェント DevOps** ($20K) | 完全なクローズドループ: CI失敗 → 検出 → 診断 → 修正 → PR → CI合格。LLM駆動のエージェント、実際のGitHub実行、MCP統合、**CGRF v3.0 Tier 2 ガバナンス**、**AGS 憲法的正義**、**AIS XP/TP 経済**、**Prometheus/Grafana モニタリング**、**VS Code 拡張**、**REFLEX 自己修復**、**Notion/Supabase ビジュアライゼーション**、**1310 テスト自動検証** |
| **ベストマルチエージェントシステム**             | A2A プロトコル、エージェントレジストリ、4つのLLM駆動エージェント (Tier 1-2)、共有メモリ、エージェントをツールとして公開するMCPサーバー                                                                                                                                                                            |
| **ベスト Microsoft Foundry の利用**      | 各エージェントをFoundryエージェントサービスとして、Azure OpenAIモデル、構造化出力スキーマ、**CGRF メタデータ統合**                                                                                                                                                                         |
| **ベストエンタープライズソリューション**           | ハッシュチェーン監査、ポリシーエンジンガバナンス、リフレックスルール、RAIフレームワーク、ウェブダッシュボード、SSEストリーミング、**CGRF CLI バリデーター**                                                                                                                                                              |
| **ベスト Azure 統合**                   | サービスバス、Cosmos DB、アプリインサイト、フォールバックチェーンを持つAzure OpenAI、**Verify Retry Automation**                                                                                                                                                                      |
| **ベスト MS AI プラットフォーム**             | Foundryエージェント + Azure OpenAI + MCPプロトコル + ウェブダッシュボード + GitHub統合 + **CGRF ガバナンスフレームワーク**                                                                                                                                                                 |

---

## テスト

```
ユニットテスト:
  tests/test_sentinel_v2.py    — 9 テスト
  tests/test_sherlock_v3.py    — 12 テスト
  tests/test_fixer_v3.py       — 13 テスト
  tests/test_guardian_v3.py    — 9 テスト
  tests/test_ags.py            — 17 テスト (フェーズ 24 + 1 AIS 統合)
  tests/test_ais.py            — 25 テスト (フェーズ 25)
  tests/test_monitoring.py     — 15 テスト (フェーズ 26)
  tests/test_cgrf_cli_json.py  — 8 テスト ✨ フェーズ 27
  tests/test_mca_engine.py     — 18 テスト ✨ MS-4
  tests/test_mca_professors.py — 21 テスト ✨ MS-4
  tests/test_mca_proposals.py  — 16 テスト ✨ MS-4
  tests/test_notion_mca_client.py  — 40 テスト ✨ MS-7
  tests/test_supabase_mca_mirror.py — 14 テスト ✨ MS-7
  tests/test_notion_bridge.py  — 21 テスト ✨ MS-7
  tests/test_generic_markdown_translator.py — ~12 テスト ✨ MS-8
  tests/test_gguf_engine.py    — ~10 テスト ✨ MS-8
  tests/contracts/             — A2A イベント JSON v1 契約テスト ✨ (修正 2026-02-28)

統合テスト (41 テスト):
  tests/integration/test_a2a_handoff.py              — 4 テスト (A2A パイプライン統合)
  tests/integration/test_sentinel_v2_integration.py  — 4 テスト (Sentinel 統合)
  tests/integration/test_sherlock_v3_integration.py  — 6 テスト (Sherlock 統合)
  tests/integration/test_fixer_v3_integration.py     — 7 テスト (Fixer 統合)
  tests/integration/test_guardian_v3_integration.py  — 8 テスト (Guardian 統合)
  tests/integration/test_memory_recall.py            — 5 テスト (メモリ統合)
  tests/integration/test_execution_verify.py         — 7 テスト (実行 & 検証統合)

E2E テスト:
  tests/test_pipeline_e2e.py   — 4 テスト (ci_failed, security_alert, deploy_failure, verify_retry)
  tests/test_a2a_protocol.py   — 5 テスト (registration, handoff, unknown agent, pipeline, trace)
  tests/test_execution.py      — 3 テスト (local backend, dry run, result store)

+ Nemesis/Mike/F993 サブシステムテスト
────────────────────────────────────────────
合計: 1310 合格 (フルスイート, 2026-03-06 現在) ✅
```

**フェーズ 23 で発見され修正されたプロダクションバグ**:

- Guardian V3 の cgrf_metadata が欠落 (`src/a2a/agent_wrapper.py`)
- Sherlock V3 MemoryHit API バグ (`src/agents/sherlock_v3.py`)
- Fixer V3 MemoryHit API バグ (`src/agents/fixer_v3.py`)

**2026-02-28 のコード品質向上で修正された問題**:

- **イベント JSON v1 A2A 契約の不整合** — `handoff_packet.py` を修正 (新しいフィールド `source_agent_id`/`target_agent_id`/`payload` + jsonschema)、`handoff_packet_contract.py` (`__post_init__` 必須フィールドチェック)、`decision_contract.py` (ISO 8601 'T' セパレーターの強制)
- **非推奨 API `datetime.utcnow()`** — Python 3.12+ での DeprecationWarning を解決。13 ファイルで `datetime.now(timezone.utc)` に置き換え。`pentest_engine.py` で naive datetime 比較のために `.replace(tzinfo=None)` を追加

```## すべてのフェーズが完了 (フェーズ 21-27 + V2→V3 統合 + エボリューション MS-1 から MS-8 への移行 + コード品質向上)

すべての計画されたフェーズとエボリューションサイクルのすべてのマイルストーンが完了しました。

**完了したエボリューションマイルストーン**:

- ✅ **MS-1**: ロードマップ IR スキーマ & タイプ定義 (31 テスト)
- ✅ **MS-2**: 3 つの翻訳者 + パイプライン (37 テスト)
- ✅ **MS-3**: ロードマップトラッカー & API (17 テスト, 既存の IR タイプを再利用)
- ✅ **MS-4**: MCA コアエンジン + 教育の書き直し (55 テスト, Bedrock E2E 確認済み)
- ✅ **MS-5**: ロードマップ IR × MCA 統合 — フィードバックループ接続
- ✅ **MS-6**: 提案実行 + SANCTUM — 自動実行の完了 (54 テスト)
- ✅ **MS-7**: Notion/Supabase ビジュアライゼーション統合 + MCA Grafana ダッシュボード (75 テスト)
- ✅ **MS-8**: 一般的な Markdown / Gitlog 翻訳者 + GGUF エンリッチメント + CI スクリプト
- ✅ **コード品質向上** (2026-02-28): イベント JSON v1 A2A 契約の修正 + `datetime.utcnow()` の計画された API クリーンアップ (13 ファイル)
- ✅ **MS-C1 から C3 + MS-A1 から A7 + MS-B1 から B3** (2026-03-06): VCC/OAD/Perplexity 統合 + Nemesis 防御システム (177 テスト)

**総テスト数**: **1310 合格** (フルスイート, 2026-03-06 現在) ✅

**次のステップ**:

- **MS-8 (スタッガーチェーン)** — `CONFIDENCE_WRAPPER` JSON 衝突問題を解決した後に開始予定 (⏸ 保留中)
- **Tier 3 (ミッションクリティカル) プロモーション** — 95% E2E テストカバレッジを目指す
- **プロダクションデプロイ** — Docker / Kubernetes / Prometheus スタックの構築

---

## ドキュメンテーション

- **統合ブループリント v9.0**: [BLUEPRINT_INTEGRATION_VCC_OAD_PERPLEXITY_v9.0.md](BLUEPRINT_INTEGRATION_VCC_OAD_PERPLEXITY_v9.0.md) - VCC/OAD/Perplexity 統合 + Nemesis 設計仕様 — 更新日: 2026-03-06
- **統合ロードマップ**: [ROADMAP_VCC_OAD_PERPLEXITY.md](ROADMAP_VCC_OAD_PERPLEXITY.md) - MS-A1 から MS-8 までの実装ロードマップ — 更新日: 2026-03-06
- **エボリューションブループリント**: [EVOLUTION_BLUEPRINT_20260226.md](EVOLUTION_BLUEPRINT_20260226.md) - MCA エボリューション設計ガイドライン (ギャップ分析、資産活用ポリシー) — 更新日: 2026-02-28
- **エボリューションロードマップ**: [EVOLUTION_ROADMAP_20260226.md](EVOLUTION_ROADMAP_20260226.md) - MS-1 から MS-8 までの開発マイルストーン — 更新日: 2026-02-28
- **MCA-META-001**: [config/mca_meta_001.yaml](config/mca_meta_001.yaml) - MCA システム憲法 (ドラフト)
- **CGRF CLI**: [src/cgrf/README.md](src/cgrf/README.md) - CLI 使用法、バリデーションチェックリスト、--json 出力
- **VS Code 拡張**: [vscode-extension/citadel-cgrf/README.md](vscode-extension/citadel-cgrf/README.md) - 拡張設定、コマンド、開発方法
- **Grafana ダッシュボード (DevOps)**: [grafana/citadel_dashboard.json](grafana/citadel_dashboard.json) - Prometheus メトリクスダッシュボード (フェーズ 26)
- **Grafana ダッシュボード (MCA)**: [grafana/mca_dashboard.json](grafana/mca_dashboard.json) - MCA 9 パネルダッシュボード (MS-7)
- **CGRF 仕様**: `blueprints/CGRF-v3.0-Complete-Framework.md` - 完全なガバナンスフレームワーク仕様
- **AGS 仕様**: `blueprints/AGS-System-Spec-v1.0.md` - エージェントガバナンスシステム仕様 (フェーズ 24 で完了)
- **AIS 仕様**: `blueprints/AIS-System-Spec-v1.0.md` - 自律指数システム仕様
- **REFLEX 仕様**: `blueprints/REFLEX-System-Spec-v1.0.md` - 自己修復仕様

---

## ライセンス

MITライセンス (ハッカソン提出用)

---

## ハッカソン提出チェックリスト

> 提出前に空欄を埋めてください。

| 要件 | 状態 | リンク / 値 |
| --- | --- | --- |
| 動作するプロジェクト | ✅ | このリポジトリ |
| プロジェクト説明 | ✅ | このREADME |
| デモ動画 (YouTube / Vimeo、公開) | ⬜ | `<!-- TODO: URLをここに貼り付け -->` |
| 公開GitHubリポジトリ | ⬜ | `<!-- TODO: GitHub URLをここに貼り付け (現在はGitLab) -->` |
| アーキテクチャ図 (PNG/SVG) | ⬜ | `<!-- TODO: docs/architecture.pngに追加してリンク -->` |
| チームメンバーのMicrosoft Learnユーザー名 | ⬜ | 以下の貢献者セクションを参照 |

---

## 貢献者

| 名前 | 役割 | Microsoft Learn ユーザー名 |
| --- | --- | --- |
| **Dmitry** | types.py, orchestrator.py, audit/report.py, A2A プロトコル, LLM 統合, メモリストア, 実行ランナー, REFLEX ディスパッチャ, CGRF v3.0 統合 | `<!-- TODO -->` |
| **kousaki (Mike)** | オリジナル MVP アーキテクチャ, V2/V3 エージェント実装, CLI バリデーター | `<!-- TODO -->` |

---