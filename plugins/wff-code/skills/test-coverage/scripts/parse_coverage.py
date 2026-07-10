#!/usr/bin/env python3
"""parse_coverage.py: parse coverage.json into a structured gap report."""

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UncoveredFunction:
    file: str
    name: str
    start_line: int
    end_line: int
    missing_lines: list[int]
    total_lines: int
    coverage_pct: float
    is_critical: bool = False


def _collect_uncovered_functions(
    filepath: str,
    missing: set[int],
    critical_modules: list[str],
    tree: ast.Module,
) -> list[UncoveredFunction]:
    """Return UncoveredFunction entries for every partially-uncovered function in tree."""
    found: list[UncoveredFunction] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_lines = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            func_missing = func_lines & missing
            if func_missing:
                total = len(func_lines)
                covered = total - len(func_missing)
                is_crit = any(m in filepath for m in critical_modules)
                found.append(
                    UncoveredFunction(
                        file=filepath,
                        name=node.name,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        missing_lines=sorted(func_missing),
                        total_lines=total,
                        coverage_pct=round(covered / total * 100, 1),
                        is_critical=is_crit,
                    )
                )
    return found


def parse_coverage(
    coverage_path: str = "coverage.json",
    _source_dir: str = "src",
    critical_modules: list[str] | None = None,
    threshold: float = 80.0,
) -> dict:
    """Parse coverage.json and return structured gap analysis."""
    critical_modules = critical_modules or []

    with open(coverage_path) as f:
        data = json.load(f)

    results = {
        "summary": {
            "total_statements": 0,
            "covered_statements": 0,
            "total_branches": 0,
            "covered_branches": 0,
        },
        "files_below_threshold": [],
        "uncovered_functions": [],
    }

    for filepath, file_data in data.get("files", {}).items():
        summary = file_data.get("summary", {})
        line_pct = summary.get("percent_covered", 100)

        results["summary"]["total_statements"] += summary.get("num_statements", 0)
        results["summary"]["covered_statements"] += summary.get(
            "num_statements", 0
        ) - summary.get("missing_lines", 0)

        if line_pct < threshold:
            results["files_below_threshold"].append(
                {
                    "file": filepath,
                    "line_coverage": line_pct,
                    "branch_coverage": summary.get("percent_covered_branches", 0),
                    "missing_lines": file_data.get("missing_lines", []),
                    "missing_branches": file_data.get("missing_branches", []),
                }
            )

        # AST analysis for uncovered functions
        source_path = Path(filepath)
        if source_path.exists():
            missing = set(file_data.get("missing_lines", []))
            try:
                tree = ast.parse(source_path.read_text())
            except SyntaxError:
                continue
            results["uncovered_functions"].extend(
                _collect_uncovered_functions(filepath, missing, critical_modules, tree)
            )

    # Sort: critical first, then by coverage ascending
    results["uncovered_functions"].sort(
        key=lambda f: (not f.is_critical, f.coverage_pct)
    )
    results["files_below_threshold"].sort(key=lambda f: f["line_coverage"])

    overall_pct = 0
    if results["summary"]["total_statements"]:
        overall_pct = round(
            results["summary"]["covered_statements"]
            / results["summary"]["total_statements"]
            * 100,
            1,
        )
    results["summary"]["overall_coverage"] = overall_pct

    return results


if __name__ == "__main__":
    report = parse_coverage(
        coverage_path=sys.argv[1] if len(sys.argv) > 1 else "coverage.json"
    )
    print(json.dumps(report, indent=2, default=vars))
