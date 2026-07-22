# school-timetable-solver

Excelで管理する校舎、教室、教師、クラス、教科、開講日、授業要求、勤務情報、固定授業、配置ルールを読み込み、Google OR-Tools CP-SATで制約を満たす時間割を生成するローカルCLIです。

## Ver.1の対象範囲

- `validate_only`による入力形式・参照・固定授業・ルール競合・明白な供給不足の検証
- `strict`による全必要授業数を満たす時間割生成
- 固定授業、教師・クラス・教室重複、カレンダー、勤務可否、許可時限、日別上限、連続コマ、連続登校、校舎移動のHard Constraint
- OR-Toolsとは独立した結果検証
- 全体、教師別、クラス別、集計、検証、実行条件、未配置を含むExcel出力
- テキスト実行ログ

## Ver.1の対象外

Soft Constraintの最適化、本格的な`diagnostic`、Unsat Core、合同授業、複数教師授業、複数時限連続授業、生徒別時間割、教室定員、Web画面、外部API、PyInstaller、実行ファイル、`.bat`、デプロイ、CIは対象外です。`diagnostic`が入力された場合は入力エラーになります。

## 必要環境

- Python 3.12以降
- uv 0.11以降

## セットアップ

```bash
uv sync
```

## サンプル実行

```bash
uv run python -m school_timetable_solver.main \
  --input projects/sample/input/時間割入力_サンプル.xlsx \
  --output projects/sample/output/時間割生成結果_サンプル.xlsx \
  --log projects/sample/output/時間割生成_サンプル.log
```

入力は`projects/sample/input/時間割入力_サンプル.xlsx`、出力は`projects/sample/output/`に作成されます。生成結果とログはGit管理対象外です。

## 品質チェック

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

## 終了コード

| Code | Meaning |
|---:|---|
| 0 | 入力検証成功、またはstrict生成成功 |
| 1 | 予期しないアプリケーションエラー、またはMODEL_INVALID |
| 2 | 入力形式・入力整合性・候補不足エラー |
| 3 | strict生成で解なし、または制限時間内に解なし |
| 4 | 独立した生成結果検証エラー |

## 設計文書

- `docs/要件定義書_v0.1_school-timetable-solver.md`
- `docs/アーキテクチャ設計書_v0.2_school-timetable-solver.md`
- `docs/基本設計書_v0.1_school-timetable-solver.md`
- `docs/コーディング規約_v0.1_school-timetable-solver.md`

実装はCodex実装指示書、要件定義書、アーキテクチャ設計書v0.2、基本設計書、コーディング規約の順で解釈しています。物理配置はアーキテクチャ設計書v0.2の中粒度構成を優先します。

## 現時点の前提と制限

- `10_教師勤務`に対象教師・日付・時限の行がない場合は勤務不可として扱います。曖昧な推測補完を避けるためです。
- 基本設計書に日付・時限別教室可否の列定義がないため、Ver.1のH14は`05_教室.enabled`とクラス所属校舎との一致で判定します。
- `05_教室`、`08_教科`、`11_固定授業`の詳細列は基本設計書に完全な表がないため、ID参照とVer.1制約に必要な最小列を採用しています。テンプレートの列見出しを正として利用してください。
- `allow_consecutive`は入力として保持しますが、要件定義書の正式Hard Constraint一覧に独立ルールがないためVer.1では制約化しません。
- 出力はVer.1用の一覧形式で、既存帳票との完全な書式一致や印刷レイアウト最適化は行いません。
