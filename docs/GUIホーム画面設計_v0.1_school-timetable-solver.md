# 時間割解決システム GUIホーム画面設計

| 項目 | 内容 |
|---|---|
| Gitプロジェクト名 | `school-timetable-solver` |
| 文書名 | GUIホーム画面設計 |
| バージョン | `v0.1` |
| 対象 | Homeプロトタイプ |
| 作成日 | 2026-08-27 |

## 1. 目的

既存のExcel入力・CLI・Solverを変更せず、WindowsおよびmacOSで利用できるローカルデスクトップアプリのHome画面を先行実装する。

本バージョンではEditor本体の入力UIは設計対象外とし、画面遷移を確認できるshellだけを用意する。

## 2. Homeフロー

```text
Home
├── 保存済みデータ一覧
│   └── 選択 → 保存済みProjectをロードしたEditor shell
├── 新規作成
│   └── 空Projectを保存 → Editor shell
└── Excelインポート
    └── 既存Readerで読込確認 → ローカル保存 → Home一覧に追加
```

Excelインポート後はEditorへ自動遷移しない。

## 3. Home機能

- 保存済みProjectを更新日時降順で表示する。
- Projectには名前、備考、作成日時、更新日時を保持する。
- 一覧からProjectを開ける。
- 新規作成時は`無題の時間割`を作成し、重複時は連番を付ける。
- Excelインポートでは既存の`CompatibleExcelInputReaderAdapter`を使用し、ERRORがあるWorkbookは保存しない。
- インポート済みWorkbookは元ファイルを参照し続けず、アプリデータ領域へコピーする。
- Homeのメニューから名前・備考変更、複製、削除を行える。

## 4. 保存方式

Project一覧の正本はSQLiteとする。SQLiteはPython標準ライブラリを使用し、追加依存は導入しない。

保存領域はQtの`QStandardPaths.AppLocalDataLocation`から取得し、OS固有パスを業務コードへハードコードしない。

保存物は概念上次の構成とする。

```text
<AppLocalDataLocation>/
├── timetable.db
└── imports/
    └── <project_id>.xlsx
```

本Homeプロトタイプでは、インポートExcelの正規化済み内部ModelをSQLiteへ永続化しない。Editor本体の保存契約を設計する際に、GUI入力データの正本を別途確定する。ExcelをGUI内部データの恒久的な正本にする設計にはしない。

## 5. 技術構成

| 領域 | 採用 |
|---|---|
| GUI | PySide6 6.8系 |
| Project metadata | SQLite (`sqlite3`) |
| OS別データパス | Qt `QStandardPaths` |
| Excel Import | 既存`CompatibleExcelInputReaderAdapter` |
| Solver | 既存実装を変更しない |

PySide6はCLI利用者へ強制しないため`desktop` optional dependencyとする。

## 6. 対応環境方針

- Windows x86_64を正式対象とする。
- macOS Intel x86_64を正式対象とする。
- macOS Apple Silicon arm64も同一ソースで対応可能な構成とする。
- PySide6 6.8系のmacOS universal2配布物を前提に、HomeプロトタイプのmacOS最低目標はmacOS 12以降とする。
- Linuxは正式サポート対象外とする。

## 7. 今回変更しないもの

- 18シートExcel入力契約
- Hard/Soft Constraint
- OR-Tools Solver
- Excel出力契約
- CLI
- Editor詳細入力画面
- 時間割生成ボタン
- Excel Export
- PyInstallerによる配布パッケージ

## 8. 受入確認

Homeプロトタイプでは次を確認する。

1. アプリが起動しHomeが表示される。
2. 新規作成で空Projectが保存されEditor shellへ遷移する。
3. Homeへ戻ると新規Projectが一覧に表示される。
4. 有効な既存ExcelをインポートするとHomeに留まり、一覧へ追加される。
5. 元Excelを移動または削除しても、アプリ側のインポート済みコピーが残る。
6. 一覧のProjectを選択すると保存済み状態でEditor shellへ遷移する。
7. 名前・備考変更、複製、削除がHomeへ反映される。
8. アプリを終了・再起動しても一覧が維持される。
