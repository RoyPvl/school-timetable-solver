# Repository Instructions

## Read before implementation

1. `docs/入力契約設計書_v0.7_school-timetable-solver.md`
2. `docs/出力契約設計書_v0.2_school-timetable-solver.md`
3. `docs/要件定義書_v0.1_school-timetable-solver.md`
4. `docs/アーキテクチャ設計書_v0.2_school-timetable-solver.md`
5. `docs/基本設計書_v0.1_school-timetable-solver.md`
6. `docs/コーディング規約_v0.1_school-timetable-solver.md`

Priority is the active implementation instruction, input contract v0.7, output contract v0.2, architecture v0.2, requirements, basic design, coding standards, then general Python practice. Architecture v0.2's medium-grained file layout overrides the older one-class-per-file rule.

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

## AI Context Hub

This repository is connected to the persistent AI Context Hub.

### Integration artifacts

`AGENTS.md` and `.ai-context.yaml` are tracked integration artifacts. Do not add either to
`.gitignore`, and do not record device-specific paths, credentials, or tokens in them.

### Mandatory task bootstrap

Before planning, answering, editing files, or making implementation decisions for every task:

1. Read `.ai-context.yaml`.
2. Resolve the Hub: `AI_KNOWLEDGE_HOME` -> sibling `../ai-knowledge` -> workspace clone -> configured GitHub access.
3. When using a local Hub clone, run `git status` and, when clean, `git pull --ff-only` before reading Context. Resolve divergence with the Hub multi-device workflow; never force-push or mechanically discard either side.
4. Read the Hub `AGENTS.md`, then this project's `overview.md` and `current-state.md` from `project.context_path`.
5. Read only task-relevant Decisions or shared Knowledge after that.
6. For Source Repository Git writes, follow `protocol.git` in `.ai-context.yaml` (or the Hub's `workflows/source-repo-git.md`).

If the Hub cannot be resolved or read, treat persistent Context as unavailable, avoid assumptions about project history, inspect the Source Repository more thoroughly, and report the limitation when material.

### AI-native Git lifecycle

Unless a stricter explicit repository policy applies, write tasks follow:

```text
sync main -> short-lived task branch -> implement / validate -> commit / push -> Pull Request
-> final merge gate -> squash merge or auto-merge -> remote / local branch cleanup
```

Creating a Pull Request is not normally completion. Before merging, re-check the final diff,
checks, reviews, conflicts, and head SHA. Do not delete dirty, local-only, open-PR, unmerged, or
uncertain branches.

### Trust and update rules

The Source Repository remains the source of truth for implementation and formal specifications.
After final integration, apply the Hub Context Delta Check. Update the Hub only for durable state,
decisions, constraints, reusable knowledge, or routing changes; commit and push any Hub update
before considering the task complete. Do not store chat transcripts, routine logs, command output,
or Pull Request history in the Hub.
