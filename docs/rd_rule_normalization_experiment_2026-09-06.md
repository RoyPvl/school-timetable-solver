# 自然言語ルール正規化 R&D 実験（2026-09-06）

## 目的

`autonomous-company#71` の bounded R&D experiment として、曖昧さを含む日本語の時間割要件を、現行 `school-timetable-solver` の入力契約 v1.1 へ安全に写像できるかを3ケースで評価する。

対象は **既存schemaへの正規化** のみであり、新しいsolver、汎用自然言語最適化基盤、顧客向けUIは作らない。

## 判定基準

PASS条件:

- 3ケースすべてを現行schemaへ表現できる。
- hard constraintを暗黙に落とさない。
- 未確定値・曖昧表現を推測で埋めず、追加確認事項として表面化できる。
- 人手修正は主にID/date等の参照値確定に限定され、ルール設計をゼロからやり直す必要がない。

## Case 1: 小学部・非受験は午前のみ

### messy requirement

> 小学生で受験クラスじゃない子は午前中だけにしてください。1〜3限ならどこでも大丈夫です。

### canonical mapping

`11_配置ルール`:

```yaml
rule_id: CLASS_ELEM_NONEXAM_AM
rule_name: 小学部非受験_午前のみ
enabled: true
constraint_type: hard
target_entity: class
condition_field: division|exam_category
condition_operator: eq|eq
condition_value: elementary|non_exam
campus_id: null
start_date: null
end_date: null
weekdays: null
allowed_periods: P1|P2|P3
daily_hard_limit: null
forbid_first_last_same_day: null
attendance_streak_limit: null
priority: 100
preferred_attendance_streak_limit: null
required_lesson_periods: null
```

### validation

入力契約の代表例にある「小学部・非受験 -> P1|P2|P3」と一致する。

### ambiguity handling

- 「午前中」がP1〜P3を意味することは、このWorkbookの既存period定義と合わせて確定する必要がある。自然言語だけから時刻境界を推測しない。
- 1日最大コマ数について言及がないため、このルールでは設定しない。別の共通ルールで解決される必要がある。

### result

PASS。hard constraintのsilent omissionなし。

---

## Case 2: 中3は8月から午前も可

### messy requirement

> 中学生は基本4〜6限でお願いします。ただ、中3だけは8月に入ったら午前も使っていいです。

### canonical mapping

`11_配置ルール` に2ルール:

```yaml
- rule_id: CLASS_JH_DEFAULT_PM
  rule_name: 中学部_通常4から6限
  enabled: true
  constraint_type: hard
  target_entity: class
  condition_field: division
  condition_operator: eq
  condition_value: junior_high
  start_date: null
  end_date: null
  allowed_periods: P4|P5|P6
  priority: 100

- rule_id: CLASS_JH3_FROM_AUG_ALL
  rule_name: 中3_8月以降全時限可
  enabled: true
  constraint_type: override
  target_entity: class
  condition_field: division|grade
  condition_operator: eq|eq
  condition_value: junior_high|3
  start_date: 2026-08-01
  end_date: null
  allowed_periods: P1|P2|P3|P4|P5|P6
  priority: 200
```

### validation

入力契約の代表例にある「中学部 -> P4|P5|P6」「中学3年・指定日以降 -> overrideでP1〜P6」と一致する。

### ambiguity handling

- 「8月に入ったら」は対象年度の `2026-08-01` と解釈可能だが、年度はWorkbookの開講カレンダーから確定する必要がある。
- 「午前も使っていい」は午後を禁止する意味ではなく、既存午後枠に午前枠を追加するため `override` でP1〜P6へ置換する。
- 8月以降の日曜・休館日等をこのルールで開講扱いにはしない。開講可否は `02_開講カレンダー` が正本。

### result

PASS。自然言語の例外をpriority/overrideへ落とせる。

---

## Case 3: 教師は前半2〜3日、後半1〜2日休み、合計4日

### messy requirement

> T001先生は夏期講習で、前半は2〜3日休み、後半は1〜2日休みにして、全部で4日は休ませたいです。できれば前半3日、後半1日がいいです。

### canonical mapping

`15_教師休日日数ルール` に2行:

```yaml
- rule_id: DAY_OFF_T001_EARLY
  teacher_id: T001
  enabled: true
  eligible_dates: <前半の明示日集合>
  required_days_off: null
  minimum_days_off: 2
  maximum_days_off: 3
  preferred_days_off: 3
  quota_group_id: SUMMER_T001
  group_required_days_off: 4

- rule_id: DAY_OFF_T001_LATE
  teacher_id: T001
  enabled: true
  eligible_dates: <後半の明示日集合>
  required_days_off: null
  minimum_days_off: 1
  maximum_days_off: 2
  preferred_days_off: 1
  quota_group_id: SUMMER_T001
  group_required_days_off: 4
```

### validation

入力契約の `15_教師休日日数ルール` 代表例と同じ構造で表現できる。期間ごとのmin/max、preferred、group合計4日を同時に持てる。

### ambiguity handling

このケースは自然言語だけでは **schema-valid rowを完成できない**。`eligible_dates` は契約上、実際の開講カレンダーに存在する日をISO日付で列挙する必要があるため、次を明示的に要求する。

1. 「前半」「後半」が具体的にどの日付集合を指すか。
2. その日付が `02_開講カレンダー.output_enabled=TRUE` であるか。
3. 同一教師について `10_教師休み` と併用していないか。

これらを推測で補完してはならない。

### result

PASS with required clarification。重要な曖昧性をsilent guessせず検出できる。

---

## 実験結果

| Case | schema表現 | hard omission | ambiguity surfaced | manual correction |
|---|---|---|---|---|
| 1 小学部午前 | 可 | なし | period意味のみ確認 | 小 |
| 2 中3 8月例外 | 可 | なし | 年度/開始日を明示 | 小 |
| 3 教師休日quota | 可 | なし | eligible_datesが必須 | 中 |

3/3ケースで現行schemaへ意味を保持した写像が可能だった。一方で、自然言語から完全自動でWorkbook rowを確定できるとは限らない。特に日付集合、参照ID、年度境界などは、**推測せず unresolved field として出すこと**が安全性の中心になる。

## setup-work reduction estimate

従来は利用者要件を読み、18-sheet契約のどのシート・列・rule semanticsへ落とすかを人が判断する必要がある。今回の3ケースでは、その判断を次の2段階へ縮約できた。

1. requirement -> candidate structured mapping
2. unresolved references / ambiguitiesだけ人が確定

したがって、少なくとも既存schemaで表現可能なルールについては、pilot onboardingの「ルール設計」作業を **確認・補正中心**へ変えられる見込みがある。ただし削減率の数値化には実顧客ルールでの測定が必要であり、本実験だけから工数削減率は推定しない。

## disposition

**`integrate`（限定的）**

次に統合すべき能力はLLM任せの自動設定ではなく、以下のcompiler contractである。

```text
messy requirement
 -> candidate mapping to existing sheet/columns
 -> unresolved/ambiguous fields
 -> deterministic schema/reference validation
 -> human confirmation only where unresolved
```

実装する場合の最初の範囲は `11_配置ルール` と `15_教師休日日数ルール` 等の既存schemaへの構造化候補生成までとし、solver本体やinput contractを変更しない。商業化判断は `autonomous-company#48` の実顧客/WTP evidenceに従う。
