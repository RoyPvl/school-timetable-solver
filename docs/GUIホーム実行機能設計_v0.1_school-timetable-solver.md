# GUIホーム実行機能設計

| 項目 | 内容 |
|---|---|
| 文書名 | GUIホーム実行機能設計 |
| システム名称 | 時間割解決システム |
| Gitプロジェクト名 | `school-timetable-solver` |
| バージョン | `v0.1` |
| 対象 | Home画面からの時間割実行 |

## 1. 目的

保存済み時間割のHome一覧から、既存の時間割生成バックエンドをGUI操作で実行できるようにする。

## 2. 画面フロー

```text
Home
  ↓ 保存済み案件の「実行」
実行設定ダイアログ
  ↓
非同期実行
  ↓
完了 / 検証エラー / 解なし / 実行エラー
```

## 3. Home一覧

各保存済み案件の右側を次の順序とする。

```text
[案件情報] [実行] [⋮]
```

現時点ではExcelインポート済み案件のみ実行可能とする。新規作成案件はEditor入力の保存契約が未実装であるため、実行ボタンを無効表示する。

## 4. 実行設定

入力ファイルは保存済み案件から自動決定し、利用者には指定させない。

既存バックエンドの引数とGUI項目は次のとおりとする。

| Backend | GUI | Default |
|---|---|---:|
| `--input` | 案件から自動決定 | - |
| `--output` | 出力Excel | Documents配下 |
| `--log` | 実行ログ | 出力Excelと同一basenameの`.log` |
| `--mode` | 実行モード | `strict` |
| `--max-solve-seconds` | 最大実行時間 | 60秒 |
| `--random-seed` | 乱数シード | 1 |
| `--num-search-workers` | 並列ワーカー数 | 8 |

`validate_only`では出力Excelを生成しないが、既存`GenerationRequestModel`との互換性のため出力パスは保持する。

## 5. 実行方式

GUIスレッドでSolverを実行しない。`QThread`上で`ExecuteProjectService`を実行し、UIは実行中ダイアログを表示する。

Solver側にキャンセル契約がないため、本バージョンでは実行中キャンセルを提供しない。

## 6. バックエンド接続

`ExecuteProjectService`は保存済み案件とGUI指定値から既存`GenerationRequestModel`を構築し、既存の`GenerateTimetableService`へ渡す。

時間割生成ロジック、Hard Constraint、Soft Constraint、既存CLI引数の意味は変更しない。

## 7. 結果表示

- `exit_code=0`かつ`VALIDATED`: 入力検証完了
- `exit_code=0`: 生成完了と出力先を表示
- その他: statusとValidation ERROR上位5件を表示
- 予期しない例外: 実行エラーとして表示

## 8. 次フェーズ

Editor入力の保存契約を設計し、新規作成案件もExcelを内部正本にせず実行可能な入力モデルへ接続する。
