# school-timetable-solver

Excelで管理する開講日、時限、校舎、教室、教師、クラス、教科、授業要求、教師勤務、配置ルールを読み込み、Google OR-Tools CP-SATでHard Constraintを満たす時間割を生成するローカルCLIです。

## PoCの対象範囲

- 入力契約v0.1の13シートExcel
- `validate_only`による形式・参照・ルール解決・明白な供給不足の検証
- `strict`による全必要授業数を満たす時間割生成
- 教師・クラス・教室重複、必要コマ数、日別上限、連続時限、連続登校、同日単一校舎のHard Constraint
- カレンダー、教師勤務、クラス許可時限、教室所属校舎のCandidate事前除外
- OR-Toolsとは独立した結果検証
- `全体`1シートの日付別時間割マトリクス出力
- テキスト実行ログ

固定授業、代替担当教師、複数担当教師、条件付き校舎移動、Soft Constraint、`diagnostic`、Unsat Core、教師別・クラス別・集計・検証結果等の補助Worksheet、GUI、実行ファイル化、デプロイ、CIはPoC対象外です。

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
  --log projects/sample/output/時間割生成_サンプル.log \
  --mode strict \
  --max-solve-seconds 60 \
  --random-seed 1
```

CLI引数:

| 引数 | 内容 | Default |
|---|---|---:|
| `--input` | 入力Excel | 必須 |
| `--output` | 出力Excel | 必須 |
| `--log` | 実行ログ | 任意 |
| `--mode` | `strict` / `validate_only` | `strict` |
| `--max-solve-seconds` | 正の実数 | `60.0` |
| `--random-seed` | 0以上の整数 | `1` |

`validate_only`ではSolverを実行せず、時間割Excelも生成しません。入力エラー、候補不足、解なし、結果検証エラー時にも出力Excelを生成・置換しません。

## 入力・出力

入力Workbookは次の13シートです。

```text
00_操作説明
01_基本設定
02_開講カレンダー
03_時限
04_校舎
05_教室
06_教師
07_クラス
08_教科
09_授業要求
10_教師勤務
11_配置ルール
12_選好設定
```

出力Workbookは`全体`シート1枚だけを持ちます。出力対象日を日付昇順に1行2日ずつ配置し、各日を校舎・教室列、6時限×クラス・教科・担当行のマトリクスで表示します。

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
| 1 | 予期しない内部エラー、Solverの予期しない状態 |
| 2 | 入力形式・入力整合性・ルール解決・候補不足エラー |
| 3 | strict生成で`INFEASIBLE`または`UNKNOWN` |
| 4 | 独立結果検証またはDocument構築エラー |

## 設計文書

- [入力契約設計書 v0.1](docs/入力契約設計書_v0.1_school-timetable-solver.md)
- [出力契約設計書 v0.1](docs/出力契約設計書_v0.1_school-timetable-solver.md)
- [要件定義書 v0.1](docs/要件定義書_v0.1_school-timetable-solver.md)
- [アーキテクチャ設計書 v0.2](docs/アーキテクチャ設計書_v0.2_school-timetable-solver.md)
- [基本設計書 v0.1](docs/基本設計書_v0.1_school-timetable-solver.md)
- [コーディング規約 v0.1](docs/コーディング規約_v0.1_school-timetable-solver.md)

実装は、作業中の修正指示、入力契約、出力契約、アーキテクチャv0.2、要件定義、基本設計、コーディング規約の順で解釈します。入出力契約と競合する旧15シート、固定授業、条件付き移動、一覧形式出力の記述は適用しません。
