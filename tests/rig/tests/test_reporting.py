"""Self-tests for junit parsing and group result classification."""

from __future__ import annotations

from pathlib import Path

from tests.rig.reporting import GroupResult, parse_junit


def _write_junit(group_dir: Path, content: str, exit_code: int) -> None:
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "junit.xml").write_text(content)
    (group_dir / "exit.txt").write_text(str(exit_code))


def test_parse_testsuites_wrapper_sums_across_suites(tmp_path: Path) -> None:
    """pytest can emit either <testsuites> or a bare <testsuite>; both must
    aggregate correctly. Otherwise multi-suite failures get undercounted and
    a broken run reports green.
    """
    _write_junit(
        tmp_path / "g",
        """<?xml version="1.0"?>
        <testsuites>
          <testsuite name="a" tests="3" failures="1" errors="0" skipped="0" time="1.0"/>
          <testsuite name="b" tests="2" failures="2" errors="0" skipped="0" time="0.5"/>
        </testsuites>
        """,
        exit_code=1,
    )
    result = parse_junit("g", "unit", tmp_path)
    assert result is not None
    assert result.passed == 2  # (3-1) + (2-2)
    assert result.failed == 3
    assert result.status == "fail"


def test_parse_single_testsuite_root(tmp_path: Path) -> None:
    _write_junit(
        tmp_path / "g",
        """<?xml version="1.0"?>
        <testsuite name="solo" tests="2" failures="0" errors="0" skipped="0" time="0.1"/>
        """,
        exit_code=0,
    )
    result = parse_junit("g", "unit", tmp_path)
    assert result is not None
    assert result.passed == 2
    assert result.status == "pass"


def test_exit_5_classified_as_empty_not_fail(tmp_path: Path) -> None:
    """pytest exit 5 = no tests collected. Optional placeholders and empty
    hurl groups both hit this; treating them as failures would falsely flag
    the whole build red.
    """
    _write_junit(
        tmp_path / "g",
        """<?xml version="1.0"?>
        <testsuite name="empty" tests="0" failures="0" errors="0" skipped="0" time="0"/>
        """,
        exit_code=5,
    )
    result = parse_junit("g", "unit", tmp_path)
    assert result is not None
    assert result.status == "empty"


def test_missing_counters_flagged_as_error(tmp_path: Path) -> None:
    """A junit.xml that parses but has no counter attributes (truncated write,
    partial flush after kill) must NOT be treated as a green zero-test run.
    """
    _write_junit(
        tmp_path / "g",
        '<?xml version="1.0"?><testsuite name="broken"/>',
        exit_code=139,  # segfault
    )
    result = parse_junit("g", "unit", tmp_path)
    assert result is not None
    assert result.errors >= 1
    assert result.status == "fail"


def test_malformed_xml_returns_error_result(tmp_path: Path) -> None:
    _write_junit(tmp_path / "g", "<not valid xml", exit_code=1)
    result = parse_junit("g", "unit", tmp_path)
    assert result is not None
    assert result.errors >= 1


def test_missing_junit_returns_none(tmp_path: Path) -> None:
    """When a group never wrote junit.xml at all (e.g. segfault before write),
    parse_junit returns None and the CLI is responsible for surfacing the
    exit code separately.
    """
    result = parse_junit("g", "unit", tmp_path)
    assert result is None


def test_status_icon_round_trips() -> None:
    pass_result = GroupResult("g", "unit", 0, 1, 0, 0, 0, 0.0)
    fail_result = GroupResult("g", "unit", 1, 0, 1, 0, 0, 0.0)
    empty_result = GroupResult("g", "unit", 5, 0, 0, 0, 0, 0.0)
    assert pass_result.status_icon == "✅"
    assert fail_result.status_icon == "❌"
    assert empty_result.status_icon == "⚪"


def test_passed_critical_path_ids_collects_only_passing_marked_tests(
    tmp_path: Path,
) -> None:
    from tests.rig.reporting import passed_critical_path_ids

    _write_junit(
        tmp_path / "g1",
        """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="4" failures="1" errors="0" skipped="1" time="1">
  <testcase classname="c" name="passes">
    <properties>
      <property name="critical_path" value="p-pass"/>
      <property name="critical_path" value="p-second"/>
    </properties>
  </testcase>
  <testcase classname="c" name="fails">
    <properties><property name="critical_path" value="p-fail"/></properties>
    <failure message="boom"/>
  </testcase>
  <testcase classname="c" name="skips">
    <properties><property name="critical_path" value="p-skip"/></properties>
    <skipped/>
  </testcase>
  <testcase classname="c" name="unmarked"/>
</testsuite></testsuites>
""",
        exit_code=1,
    )
    ids = passed_critical_path_ids("g1", tmp_path)
    assert ids == {"p-pass", "p-second"}


def test_passed_critical_path_ids_missing_or_malformed_junit(tmp_path: Path) -> None:
    from tests.rig.reporting import passed_critical_path_ids

    assert passed_critical_path_ids("absent", tmp_path) == set()
    _write_junit(tmp_path / "broken", "<testsuite", exit_code=1)
    assert passed_critical_path_ids("broken", tmp_path) == set()
