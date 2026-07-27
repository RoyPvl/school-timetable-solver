# Repository Instructions

## Read before implementation

1. `docs/入力契約設計書_v0.3_school-timetable-solver.md`
2. `docs/出力契約設計書_v0.2_school-timetable-solver.md`
3. `docs/要件定義書_v0.1_school-timetable-solver.md`
4. `docs/アーキテクチャ設計書_v0.2_school-timetable-solver.md`
5. `docs/基本設計書_v0.1_school-timetable-solver.md`
6. `docs/コーディング規約_v0.1_school-timetable-solver.md`

Priority is the active implementation instruction, input contract v0.3, output contract v0.2, architecture v0.2, requirements, basic design, coding standards, then general Python practice. Architecture v0.2's medium-grained file layout overrides the older one-class-per-file rule.

## Placement and public methods

- External Excel schema/conversion: `adapter/excel_input_adapter.py`; Reader public method `read()`.
- Excel result layout: `adapter/excel_output_adapter.py`; generate the one-sheet date matrix from `TimetableDocumentModel`; Writer public method `write()`.
- Input meaning checks: `validator/input_validators.py`; Validator public method `validate()`.
- Rule resolution and single-candidate rejection: `service/planning_services.py`; Service public method `execute()`.
- CP-SAT expressions: `constraint/hard_constraints.py`; one business rule per Constraint class with `rule_id` and `apply()`.
- Solver orchestration: `service/solver_service.py`; Service public method `execute()`.
- Independent result verification: `service/result_services.py`; Service public method `execute()`.
- Excel-independent output document construction: `service/result_services.py`; Service public method `execute()`.
- Use-case sequencing: `service/generation_services.py`; Service public method `execute()`.
- Dependency construction: `composition.py`; public methods are `create_<use_case>_service()`.

OR-Tools may be imported only from `constraint/` and `service/solver_service.py`. openpyxl may be imported only from `adapter/` and tests. Models use only the standard library.

## Required principles

- Keep years, dates, campus/class/teacher names, allowed periods, limits, and calendar exceptions data-driven through Excel.
- Every Constraint and independent violation must carry the formal `rule_id`.
- Candidate generation handles facts decidable from one candidate. Constraints handle conditions requiring simultaneous selection state. Independent result validation rechecks all Hard Constraints without OR-Tools.
- Do not create `utils.py`, `helpers.py`, `helper.py`, `manager.py`, `processor.py`, `common.py`, `base.py`, or `core.py`.
- Do not add generic repositories, DI containers, service locators, unnecessary factories/protocols/base classes, Constraint inheritance, or future-only files.
- Do not create a separate strict/diagnostic solver.
- Tests, Ruff format/lint, pyright, and sample End-to-End execution are mandatory for changes.

Before implementation, identify changed files, major classes, public methods, formal `rule_id`, validations and their placement reason, and tests. Search for existing equivalent responsibilities before adding code.
