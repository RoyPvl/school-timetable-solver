from __future__ import annotations

import ast
from pathlib import Path

from school_timetable_solver.constraint.hard_constraints import DEFAULT_HARD_CONSTRAINTS
from school_timetable_solver.constraint.soft_constraints import DEFAULT_SOFT_CONSTRAINTS

SOURCE_ROOT = Path("src/school_timetable_solver")
FORBIDDEN_FILES = {
    "utils.py",
    "helpers.py",
    "helper.py",
    "manager.py",
    "processor.py",
    "common.py",
    "base.py",
    "core.py",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_layer_import_rules_and_forbidden_module_names() -> None:
    assert not {path.name for path in SOURCE_ROOT.rglob("*.py")} & FORBIDDEN_FILES
    for path in SOURCE_ROOT.rglob("*.py"):
        imports = _imports(path)
        relative = path.relative_to(SOURCE_ROOT)
        layer = relative.parts[0]
        if layer == "model":
            assert not any(
                name.startswith(
                    (
                        "openpyxl",
                        "ortools",
                        "school_timetable_solver.service",
                        "school_timetable_solver.adapter",
                        "school_timetable_solver.validator",
                        "school_timetable_solver.constraint",
                    )
                )
                for name in imports
            )
        elif layer == "service":
            assert not any(name.startswith("openpyxl") for name in imports)
        elif layer == "validator":
            assert not any(name.startswith(("openpyxl", "ortools")) for name in imports)
        elif layer == "adapter":
            assert not any(
                name.startswith("school_timetable_solver.constraint") for name in imports
            )


def test_internal_import_graph_has_no_cycle() -> None:
    graph: dict[str, set[str]] = {}
    for path in SOURCE_ROOT.rglob("*.py"):
        module = ".".join(path.with_suffix("").relative_to("src").parts)
        graph[module] = {
            imported
            for imported in _imports(path)
            if imported.startswith("school_timetable_solver")
        }
    visited: set[str] = set()
    active: set[str] = set()

    def visit(module: str) -> None:
        if module in active:
            raise AssertionError(f"circular import: {module}")
        if module in visited:
            return
        active.add(module)
        for dependency in graph.get(module, set()):
            visit(dependency)
        active.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)


def test_hard_constraint_registration_has_unique_formal_rule_ids() -> None:
    rule_ids = [constraint.rule_id for constraint in DEFAULT_HARD_CONSTRAINTS]
    assert len(rule_ids) == len(set(rule_ids))
    assert set(rule_ids) == {
        "H01",
        "H02",
        "H03",
        "H06",
        "H07",
        "H08",
        "H09",
        "H10",
        "H11",
        "H15",
        "H16",
        "H17",
        "H18",
        "H19",
    }
    assert all(callable(constraint.apply) for constraint in DEFAULT_HARD_CONSTRAINTS)


def test_soft_constraint_registration_has_unique_formal_rule_ids() -> None:
    rule_ids = [constraint.rule_id for constraint in DEFAULT_SOFT_CONSTRAINTS]
    assert len(rule_ids) == len(set(rule_ids))
    assert set(rule_ids) == {
        "S10",
        "S11",
        "S12",
        "S13",
        "S14",
        "S15",
        "S16",
        "S17",
        "S18",
    }
    assert all(callable(constraint.apply) for constraint in DEFAULT_SOFT_CONSTRAINTS)
