# GUI Editor 保存・検証・生成契約 v0.1

## 完了条件

新規作成・Excel取り込みの両方で、編集内容を保存して再読込できる。生成は保存された編集値を使い、Excel入力の再読込を必要としない。途中入力は保存できるが、入力確認に失敗した状態ではSolver・Excel出力へ進まない。

## データの正本

案件ごとの `ProjectDocumentModel` をSQLiteの `project_documents` に保存する。マスタも案件内のスナップショットとし、他案件への暗黙同期は行わない。既存の案件複製を前回データの引継ぎとして使う。名前と備考は `projects` のメタデータが正本。

保存列は `project_id`, `document_schema_version`, `input_contract_version`, `payload_json`, `revision`, `updated_at`。文書形式は1で開始し、Excel契約版と別に管理する。未知の文書版・不正なJSON構造は読込エラーとし、保存データを変更しない。実在しない旧版への推測による移行は実装しない。

`Draft*Model` は各業務行を明示した型で持つ。数値・日付・時刻・複数値は入力途中の文字列も保存し、実行境界で変換する。真偽値はbool。内部IDは新規行追加時に自動生成し、参照選択肢のデータにはIDを持たせる。表示名から逆引きしない。教師・教科の空欄出力名、同名の別エンティティを区別する。画面の行番号・集計値は保存しない。

マスタに存在する有効行を編集対象とし、インポート時の無効行は文書に保持して選択肢から除外する。並べ替え操作は校舎・教室・時限の出力順も更新する。

## 保存と移行

- 画面入力は直接Draft行へ結び付ける。ページ下部の「保存」で記録し、「キャンセル」で最後に保存した内容へ戻す。非表示のTableItemへ入力値を複製しない。
- Editorが保存済み文書のスナップショットと編集中の文書を保持し、差分から未保存状態を判定する。保存成功時だけスナップショットを更新する。
- ページ・マスタ/配置条件タブ・一覧への移動、再読込、アプリ終了で未保存なら確認する。「はい」は破棄して続行、「いいえ」およびダイアログを閉じる操作は移動・終了を取り消す。既定選択は「いいえ」。移動先を確定する前に確認し、拒否した場合は入力widgetと値を保持する。
- 案件作成・インポート・複製ではメタデータと文書を同じSQLiteトランザクションで作る。
- 保存はrevision一致を確認してトランザクション内で進める。古い画面による上書きを拒否する。
- 保存失敗時は「未保存」とエラーを表示して編集内容を保持する。移動・終了には通常と同じ破棄確認を適用する。入力確認・生成は未保存なら保存を案内し、暗黙の保存や破棄は行わない。
- 既存のExcel取り込み案件に文書がない場合のみ、最初の読込で既存Readerから文書を作る。失敗時は空文書へ置き換えない。
- 取り込んだExcelは監査用コピー。文書保存後は生成の正本として使わない。
- 複製は独立した文書を作り、削除は外部キーのcascadeで文書も削除する。

## 処理経路と配置

| 責務 | ファイル・公開API | 理由 |
|---|---|---|
| 保存可能なDraft | `model/project_document_models.py` の `ProjectDocumentModel` / `Draft*Model` | 標準ライブラリのみ。Qt・SQLite・Solverから独立 |
| JSON境界 | `adapter/project_document_codec.py` の encode/decode関数 | 外部保存形式の型・版を確認 |
| SQLite | `adapter/project_store_adapter.py` の `load_document()` / `save_document()` / `create()` | 既存の案件保存境界へ文書を同居 |
| Import変換 | `service/project_document_services.py` の `ImportProjectDocumentService.execute()` | Excel非依存の内部モデル間変換 |
| 読込・保存 | 同ファイルの `LoadProjectDocumentService.execute()` / `SaveProjectDocumentService.execute()` | 旧案件移行と保存ユースケース |
| 実行用変換 | 同ファイルの `BuildProjectInputService.execute()` | Draftの形式検証を通してInputDataModelへ変換 |
| Draft形式検証 | `validator/input_validators.py` の `ProjectDocumentValidator.validate()` | `DOCUMENT_FIELD_REQUIRED` / `DOCUMENT_FIELD_FORMAT` を項目ごとに提示 |
| 業務検証 | 既存 `ReferenceIntegrityValidator` / RuleResolver / CapacityFeasibilityValidator | 参照・条件・供給不足の判定を再利用 |
| 生成 | `service/generation_services.py` の `GenerateFromInputDataService.execute()` | CLIとDesktopで同一の検証・Solver・独立検証・出力経路 |
| CLI境界 | 同ファイルの `GenerateTimetableService.execute()` | 既存Readerとパス競合判定を維持 |
| Desktop実行 | `service/project_services.py` の `ExecuteProjectService.execute()` | 保存文書を使って共通生成処理へ渡す |
| 画面 | `ui/editor_workspace.py`, `editor_widgets.py`, `seasonal_desktop_window.py` | 明示フィールドbinding、参照ID、派生集計、未保存状態 |
| 非同期完了 | `ui/desktop_window.py` の `ProjectRunResultReceiver` | Windowのoverrideに依存せずGUIスレッドで結果表示・終了処理 |
| 構築 | `composition.py`, `desktop_composition.py` の既存create API | 既存compositionへ依存を集約 |

Hard/Softの正式rule_idと意味は変更しない。入力確認も既存 `validate_only` と同じ候補不足判定まで通し、Solverと出力Writerは実行しない。結果検証は既存のOR-Tools非依存の検証を使う。

## 検証

- 全入力項目の文書・JSON・内部モデル往復。
- 不完全Draftの保存・再読込、項目ごとの形式エラー、未知の文書版を変更しないこと。
- revision競合の上書き拒否、複製の独立性、文書削除。
- 元Excelを削除後の編集済み文書からの生成。
- Qt offscreenで授業回数の明示保存・集計、同名教師のID選択、マスタ追加・削除、日程作成と既存編集の保持。
- Qt offscreenでキャンセル、ページ/タブ/一覧/再読込/終了時の確認の両回答、拒否時のwidget保持、保存競合、未保存実行の停止を確認。
- Qt offscreenで新規案件の画面入力からQThread実行・独立検証済みExcel出力・スレッド終了まで。
- 全pytest、Ruff format/lint、pyright、追跡済みサンプルのCLI End-to-End。

品質確認の前提として、PR #20で用意されたExcel v2境界の型絞り込みとテストの現行ポリシー整合を取り込む。Solverルールは変更しない。旧プロトタイプ専用のヘッダ推測によるwidget後付け処理は、明示bindingへの移行に伴って削除する。
