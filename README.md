# school-timetable-solver

Excelで管理する開講日、時限、校舎、教室、教師、クラス、教科、授業要求、教師勤務、配置ルールを読み込み、Google OR-Tools CP-SATでHard Constraintを満たす時間割を生成するローカルCLIです。

## PoCの対象範囲

- 入力契約v0.1の13シートExcel
- `validate_only`による形式・参照・ルール解決・明白な供給不足の検証
- `strict`による全必要授業数を満たす時間割生成
- 教師・クラス・教室重複、必要コマ数、日別上限、連続時限、連続登校、同日単一校舎、同一クラス・同日単一教室、クラス授業間の連続2コマ以上の空き禁止のHard Constraint
- 同一クラスの同日授業を連続ブロックへ寄せ、同一教室を連続時限で別クラスへ交替する回数を減らすSoft Constraint
- カレンダー、教師勤務、クラス許可時限、無効校舎のCandidate事前除外
- 日時決定と教室割当の分離による、同等教室の対称性を除いた探索
- OR-Toolsとは独立した結果検証
- `全体`1シートの日付別時間割マトリクス出力
- テキスト実行ログ

固定授業、代替担当教師、複数担当教師、条件付き校舎移動、S10・S11以外のSoft Constraint、`diagnostic`、Unsat Core、教師別・クラス別・集計・検証結果等の補助Worksheet、GUI、実行ファイル化、デプロイ、CIはPoC対象外です。

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
  --random-seed 1 \
  --num-search-workers 8
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
| `--num-search-workers` | 1以上の並列探索数。再現性優先時は`1` | `8` |

`validate_only`ではSolverを実行せず、時間割Excelも生成しません。入力エラー、候補不足、解なし、結果検証エラー時にも出力Excelを生成・置換しません。

現入力契約では、同一校舎内の有効教室に定員・用途・日時別可用性の差がありません。そのためCandidateへ実教室IDは持たせず、CP-SAT内でクラス・日付ごとの匿名教室番号だけを決めます。H15により同じクラスの同日中の授業は同じ匿名教室とし、H03により同時刻の重複を禁止します。H16は同一クラスの授業間に連続2コマ以上の空きを禁止し、空き1コマは許可します。S11は空き1コマを含む分割日を減らし、S10は同じ教室を連続時限で別クラスへ交替する回数を減らします。SolverはS11を先に最小化して日時解を固定し、残り時間で匿名教室番号に関するS10を最小化します。解の後で匿名教室番号を`output_order`順の実教室IDへ変換し、Hard Constraintを独立再検証します。

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
