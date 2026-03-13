# Auto-Execution & Auto-Merge Guide

## 概要

Citadel Lite の自動実行・自動マージ機能により、低リスクの修正を完全自動化できます。

- **自動実行**: Guardian が承認した修正を自動的に実行（PR作成）
- **自動マージ**: CI通過後、低リスク修正を自動的にマージ
- **人間の判断**: 問題がある場合（セキュリティリスク、想定外のトラブルなど）は人間の判断を求める

## ON/OFF スイッチ

### 1. 自動実行の ON/OFF

`config/settings.yaml` を編集:

```yaml
auto_execution:
  enabled: true  # false で無効化
```

### 2. 自動マージの ON/OFF

```yaml
auto_execution:
  auto_merge:
    enabled: true  # false で無効化
```

### 3. 環境変数での制御

設定ファイルを編集せずに環境変数でも制御可能:

```bash
# 自動実行を無効化
export AUTO_EXECUTION_ENABLED=false

# 自動マージのみ無効化
export AUTO_MERGE_ENABLED=false
```

## リスクベースの自動判断

Guardian V3 が算出するリスクスコアに基づいて自動的に判断:

| Risk Score | Guardian の判定 | 自動実行 | 自動マージ | 説明 |
|------------|----------------|---------|-----------|------|
| < 0.25 | `approve` | ✅ Yes | ✅ Yes | 低リスク → 完全自動化 |
| 0.25 - 0.65 | `need_approval` | ⏸️ Wait | ❌ No | 中リスク → 人間の判断を待つ |
| >= 0.65 | `block` | ❌ No | ❌ No | 高リスク → ブロック |

## 自動マージの条件

以下の**すべての条件**を満たす場合のみ自動マージされます:

1. ✅ Guardian の判定が `approve`
2. ✅ リスクスコア < 0.25
3. ✅ CI ステータスが `success`
4. ✅ 除外ブランチ（main/master/production）ではない
5. ✅ 除外イベントタイプ（security_alert/deploy_failed）ではない

## 例外設定（常に人間の判断を求める）

### ブランチ除外

```yaml
auto_execution:
  auto_merge:
    exclude_branches:
      - main
      - master
      - production
```

### イベントタイプ除外

```yaml
auto_execution:
  auto_merge:
    exclude_event_types:
      - security_alert      # セキュリティの脆弱性
      - deploy_failed       # デプロイ失敗
```

### セキュリティ脆弱性の扱い

セキュリティアラートは自動的に中リスク以上に分類され、**必ず人間の判断を求めます**:

- `severity: critical` → 自動的に `need_approval`
- `security_vulnerability` シグナルあり → リスクスコア +0.2

## 動作フロー

```
イベント発生
    ↓
Sentinel → Sherlock → Fixer → Guardian
                                  ↓
                        リスクスコア算出
                                  ↓
                    ┌─────────────┴─────────────┐
                    │                           │
            risk < 0.25              risk 0.25-0.65        risk >= 0.65
            approve                 need_approval             block
                    │                           │                │
                    ↓                           ↓                ↓
            自動実行 (PR作成)          人間の判断を待つ          実行拒否
                    ↓
            CI 実行 (自動)
                    ↓
            ┌──────┴──────┐
            │             │
       CI success    CI failure
            │             │
            ↓             ↓
        自動マージ      マージせず
        (squash)       (PR残す)
            ↓             ↓
        完了！        人間が確認
```

## CI タイムアウト設定

```yaml
auto_execution:
  auto_merge:
    ci_wait_timeout: 300  # 秒 (デフォルト: 5分)
```

CI が指定時間内に完了しない場合、自動マージはスキップされ、PR はそのまま残ります。

## マージ方法の選択

```yaml
auto_execution:
  auto_merge:
    merge_method: squash  # squash | merge | rebase
```

- `squash`: すべてのコミットを1つにまとめる（デフォルト）
- `merge`: マージコミットを作成
- `rebase`: リベース＆マージ

## ログと監査

すべての自動実行・自動マージは監査ログに記録されます:

```
out/<event_id>/
  ├── handoff_packet.json      # パイプライン全体の記録
  ├── decision.json            # Guardian の判定
  ├── execution_outcome.json   # 実行結果（PR作成）
  ├── auto_merge_result.json   # 自動マージ結果
  └── audit_report.json        # 監査レポート
```

## トラブルシューティング

### Q: 自動マージがスキップされた

A: 以下を確認:
1. `config/settings.yaml` で `auto_merge.enabled: true` か？
2. リスクスコアが 0.25 未満か？
3. イベントタイプが除外リストに含まれていないか？
4. ブランチが除外リストに含まれていないか？

監査ログで詳細を確認:
```bash
cat out/<event_id>/audit_report.json | jq '.reflex_rules_triggered'
```

### Q: CI がタイムアウトした

A: `ci_wait_timeout` を延長:
```yaml
auto_execution:
  auto_merge:
    ci_wait_timeout: 600  # 10分に延長
```

### Q: 緊急で自動マージを止めたい

A: 環境変数で即座に無効化:
```bash
export AUTO_MERGE_ENABLED=false
python -m src.orchestrator_v3 demo/events/ci_failed.sample.json
```

## セキュリティとコンプライアンス

- **監査トレイル**: すべての自動実行は SHA-256 ハッシュチェーンで記録
- **ポリシー準拠**: `src/governance/policies.yaml` の自動マージルールに準拠
- **リスク閾値**: Guardian V3 の厳格なリスク評価に基づく判断
- **人間の監視**: 中リスク以上は必ず人間の判断を求める

## ベストプラクティス

1. **段階的な導入**: まず `auto_execution.enabled: true` のみ有効化し、自動実行を確認
2. **リスク閾値の調整**: 最初は `max_risk_threshold: 0.15` など保守的に設定
3. **除外リストの拡充**: 本番環境に近いブランチは除外リストに追加
4. **監査ログの定期確認**: 自動マージの成功率とリスクスコア分布を監視
5. **CI の高速化**: タイムアウトを避けるため CI を 3分以内に完了させる

## まとめ

- **ON/OFF は config/settings.yaml で簡単に切り替え可能**
- **リスクスコア < 0.25 のみ自動マージ（安全第一）**
- **セキュリティリスク・本番ブランチは必ず人間の判断を求める**
- **すべての動作は監査ログに記録され、追跡可能**
