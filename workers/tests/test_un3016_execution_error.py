"""UN-3016: an ERROR execution must record WHY it failed.

The execution row used to be written with status=ERROR and a blank
error_message, so a failed run gave the user no reason at all. These tests
pin the summary helper that now supplies that reason, and assert the reason
survives the call that builds it.

conftest loads .env.test before collection, so importing callback.tasks here
works the same way it does in test_pg_callback_duplicate_guard.py.
"""

from unittest.mock import MagicMock, patch

import pytest

import callback.tasks as _tasks_module
from callback.tasks import (
    _EXECUTION_ERROR_MAX_LENGTH as MAX_LEN,
)
from callback.tasks import (
    _determine_execution_status_unified,
)
from callback.tasks import (
    _summarize_file_errors as summarize,
)


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


def _all_failed_batch():
    """One batch, one file, that file errored — the UN-3016 shape."""
    return [
        {
            "total_files": 1,
            "successful_files": 0,
            "failed_files": 1,
            "execution_time": 1.0,
            "file_results": [
                {
                    "status": "error",
                    "file_name": "Villa Bella.xlsm",
                    "error": "Workflow error: Execution: unstract/api/org_x/e/x.xlsm",
                }
            ],
        }
    ]


def test_status_function_returns_a_reason():
    """The real call must hand back a non-blank reason, not just a 4-tuple.

    This is what the defect actually was: the tuple gained a fourth slot but
    an always-None fourth slot would still leave the execution row blank, so
    assert on the value rather than on the shape.
    """
    api_client = MagicMock()
    with patch(
        "callback.tasks.WallClockTimeCalculator.calculate_execution_time",
        return_value=1.0,
    ):
        _, final_status, _, error_message = _determine_execution_status_unified(
            file_batch_results=_all_failed_batch(),
            api_client=api_client,
            execution_id="e-1",
            organization_id="org-1",
        )

    assert final_status == "ERROR"
    assert error_message, "an ERROR execution must carry a reason (UN-3016)"
    assert "Villa Bella.xlsm" in error_message
    assert len(error_message) <= MAX_LEN


def test_timeout_failure_also_returns_a_reason():
    """The other ERROR branch must carry a reason too.

    _determine_execution_status_unified marks ERROR from two places; a blank
    error_message from either one is the UN-3016 defect. This covers the
    timeout branch: files were expected but no batch result came back at all.
    """
    api_client = MagicMock()
    api_client.get_workflow_execution.return_value.success = True
    api_client.get_workflow_execution.return_value.data = {"total_files": 3}

    with patch(
        "callback.tasks.WallClockTimeCalculator.calculate_execution_time",
        return_value=0.0,
    ):
        _, final_status, expected_files, error_message = (
            _determine_execution_status_unified(
                file_batch_results=[],
                api_client=api_client,
                execution_id="e-2",
                organization_id="org-1",
            )
        )

    assert final_status == "ERROR"
    assert expected_files == 3
    assert error_message, "a timed-out execution must carry a reason (UN-3016)"
    assert "3" in error_message
    assert len(error_message) <= MAX_LEN


def test_no_caller_passes_a_hardcoded_none_error():
    """Regression guard: the blank error_message was the UN-3016 defect.

    Scoped to the two callback bodies that consume the status tuple, and matched
    on the AST rather than on the source text, so an unrelated keyword default
    elsewhere in the module cannot trip it. Detects the literal `error_message=None`
    keyword only — a positional None, an indirected variable, or a `**kwargs`
    splat would pass; all three defect sites were the literal form.

    Source-shape rather than behavioural because it guards the *call sites*:
    the behavioural cover for the value itself is
    test_status_function_returns_a_reason above.
    """
    import ast
    from pathlib import Path

    tasks_py = Path(_tasks_module.__file__)
    tree = ast.parse(tasks_py.read_text())
    callers = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name in {"_process_batch_callback_core", "process_batch_callback_api"}
    ]
    assert len(callers) == 2, "both callback entry points must exist"

    offenders = [
        f"{fn.name}:{kw.value.lineno}"
        for fn in callers
        for call in ast.walk(fn)
        if isinstance(call, ast.Call)
        for kw in call.keywords
        if kw.arg == "error_message"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is None
    ]
    assert not offenders, (
        f"error_message=None reintroduced at {offenders}; the execution row would "
        "record ERROR with no reason (UN-3016)"
    )
