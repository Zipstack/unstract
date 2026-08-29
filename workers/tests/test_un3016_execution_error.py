"""UN-3016: an ERROR execution must record WHY it failed.

The execution row used to be written with status=ERROR and a blank
error_message, so a failed run gave the user no reason at all. These tests
pin the summary helper that now supplies that reason.

The helper is extracted with `ast` rather than imported, because importing
workers.callback.tasks pulls in celery and the whole worker runtime.
"""

import ast
from pathlib import Path

import pytest

_TASKS = Path(__file__).resolve().parents[1] / "callback" / "tasks.py"


def _load_helper():
    """Exec just the helper and its constants out of callback/tasks.py."""
    tree = ast.parse(_TASKS.read_text())
    ns: dict = {"Any": object}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "").startswith(("_MAX_ERRORS", "_EXECUTION_ERROR"))
            for t in node.targets
        ):
            exec(compile(ast.Module([node], []), "<helper>", "exec"), ns)
        elif isinstance(node, ast.FunctionDef) and node.name == "_summarize_file_errors":
            exec(compile(ast.Module([node], []), "<helper>", "exec"), ns)
    return ns["_summarize_file_errors"], ns["_EXECUTION_ERROR_MAX_LENGTH"]


summarize, MAX_LEN = _load_helper()


def test_real_un3016_error_is_surfaced():
    """The actual Moody's failure shape must produce a non-blank reason."""
    aggregated = {
        "errors": {
            "Villa Bella.xlsm": (
                "Workflow error: Execution: unstract/api/org_x/e/x.xlsm; "
                "Destination: unstract/execution/org_x/e/METADATA.json"
            )
        }
    }
    result = summarize(aggregated, 1)
    assert result.strip()
    assert "Villa Bella.xlsm" in result
    assert "Workflow error" in result


@pytest.mark.parametrize(
    "aggregated",
    [
        {},
        {"errors": {}},
        {"errors": {"a.pdf": "", "b.pdf": None}},
    ],
)
def test_never_returns_blank(aggregated):
    """Whatever the input, the execution must never get an empty reason."""
    assert summarize(aggregated, 2).strip()


def test_reports_each_failing_file():
    result = summarize({"errors": {"a.pdf": "boom", "b.pdf": "bang"}}, 2)
    assert "a.pdf" in result
    assert "b.pdf" in result


def test_caps_number_of_reported_errors():
    errors = {f"f{i}.pdf": f"err{i}" for i in range(10)}
    result = summarize({"errors": errors}, 10)
    assert "more)" in result
    assert result.count("f9.pdf") == 0  # beyond the cap


def test_fits_the_database_column():
    """error_message is CharField(256) and truncates SILENTLY."""
    errors = {f"file_{i}_{'x' * 80}.pdf": "y" * 200 for i in range(5)}
    result = summarize({"errors": errors}, 5)
    assert len(result) <= MAX_LEN
    assert result.endswith("...")


def test_status_function_returns_a_reason():
    """_determine_execution_status_unified must return a 4-tuple."""
    tree = ast.parse(_TASKS.read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name == "_determine_execution_status_unified"
    )
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert returns, "function must return"
    assert all(
        isinstance(r.value, ast.Tuple) and len(r.value.elts) == 4 for r in returns
    ), "every return must carry (results, status, expected_files, error_message)"


def test_no_caller_passes_a_hardcoded_none_error():
    """Regression guard: the blank error_message was the UN-3016 defect."""
    source = _TASKS.read_text()
    assert "error_message=None" not in source
