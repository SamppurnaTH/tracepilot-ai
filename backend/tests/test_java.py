"""Java/Maven support without running Maven: report parsing, exclusions, selectors, scoping, regression-test rules."""

import json
from pathlib import Path

import pytest

from app.agent import JAVA_TEST_PATH, Investigation
from app.sandbox import Sandbox, detect_kind, is_generated
from app.tools import EXCLUDES_FILE, Workspace

REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.acme.ShipServiceTest" tests="4" failures="1" errors="2" skipped="1">
  <testcase classname="com.acme.ShipServiceTest" name="createsShip" time="0.1"/>
  <testcase classname="com.acme.ShipServiceTest" name="editWindowIsTenMinutes" time="0.1">
    <failure message="expected: &lt;10&gt; but was: &lt;600&gt;" type="org.opentest4j.AssertionFailedError">trace</failure>
  </testcase>
  <testcase classname="com.acme.ShipServiceTest" name="nullProject" time="0.1">
    <error message="Cannot invoke getId() because project is null" type="java.lang.NullPointerException">trace</error>
  </testcase>
  <testcase classname="com.acme.ShipServiceTest" name="needsMongo" time="0.1">
    <error message="Timed out after 30000 ms" type="com.mongodb.MongoTimeoutException">Connection refused</error>
  </testcase>
  <testcase classname="com.acme.ShipServiceTest" name="disabled" time="0"><skipped/></testcase>
</testsuite>
"""


def java_project(tmp_path: Path) -> Path:
    root = tmp_path / "svc"
    (root / "src/main/java/com/acme").mkdir(parents=True)
    (root / "src/test/java/com/acme").mkdir(parents=True)
    (root / "pom.xml").write_text("<project/>")
    (root / "src/main/java/com/acme/ShipService.java").write_text("package com.acme;\nclass ShipService {}\n")
    (root / "src/test/java/com/acme/ShipServiceTest.java").write_text("class ShipServiceTest { @Test void a() {} }\n")
    (root / "src/test/java/com/acme/RepoIT.java").write_text("@SpringBootTest\nclass RepoIT {}\n")
    (root / "src/test/java/com/acme/MongoTest.java").write_text("@Testcontainers\nclass MongoTest {}\n")
    return root


def test_detect_kind(tmp_path):
    assert detect_kind(java_project(tmp_path)) == "maven"
    assert detect_kind(tmp_path) == "python"


def test_network_tests_are_excluded_and_reported(tmp_path):
    with Sandbox(java_project(tmp_path), isolation="process", app=None, kind="maven") as sb:
        ws = Workspace(sb)
        assert ws.excluded == ["MongoTest", "RepoIT"]
        assert (sb.root / EXCLUDES_FILE).read_text() == "**/MongoTest.java\n**/RepoIT.java\n"
        assert "Excluded 2 test classes" in ws.brief([], {}, {})


def test_surefire_reports_map_to_outcomes(tmp_path):
    with Sandbox(java_project(tmp_path), isolation="process", app=None, kind="maven") as sb:
        reports = sb.root / "target" / "surefire-reports"
        reports.mkdir(parents=True)
        (reports / "TEST-com.acme.ShipServiceTest.xml").write_text(REPORT)
        outcomes, reasons = Workspace(sb)._surefire_results()
    assert outcomes == {
        "com.acme.ShipServiceTest#createsShip": "passed",
        "com.acme.ShipServiceTest#editWindowIsTenMinutes": "failed",
        "com.acme.ShipServiceTest#nullProject": "failed",  # an exception from the code under test reproduces a bug
        "com.acme.ShipServiceTest#needsMongo": "error",  # a broken environment does not
    }
    assert "expected: <10> but was: <600>" in reasons["com.acme.ShipServiceTest#editWindowIsTenMinutes"]


def test_maven_selectors():
    assert Workspace._maven_selector("src/test/java/com/acme/FooTest.java") == "FooTest"
    assert Workspace._maven_selector("FooTest#bar") == "FooTest#bar"
    with pytest.raises(ValueError):
        Workspace._maven_selector("FooTest; rm -rf /")


def test_scope_and_agent_tests_define_the_suite(tmp_path):
    with Sandbox(java_project(tmp_path), isolation="process", app=None, kind="maven", test_scope=["ShipServiceTest"], test_args=["-Dspring.profiles.active=test", "deploy"]) as sb:
        ws = Workspace(sb)
        ws.extra_tests.append("EditWindowRegressionTest")
        seen = {}
        sb.run = lambda argv, stdin=None, timeout=0: seen.setdefault("argv", argv)  # capture instead of running Maven
        ws._mvn()
    assert "-Dtest=ShipServiceTest,EditWindowRegressionTest" in seen["argv"]
    assert "-Dspring.profiles.active=test" in seen["argv"] and "deploy" not in seen["argv"]  # only -D properties pass


def test_build_output_never_enters_a_patch(tmp_path):
    with Sandbox(java_project(tmp_path), isolation="process", app=None, kind="maven") as sb:
        (sb.root / "target" / "surefire-reports").mkdir(parents=True)
        (sb.root / "target" / "surefire-reports" / "TEST-x.xml").write_text(REPORT)
        Workspace(sb)  # writes the excludes file
        assert sb.diff() == ""
    assert is_generated(Path("target/classes/A.xml")) and not is_generated(Path("src/main/A.java"))


def test_java_regression_test_paths():
    assert JAVA_TEST_PATH.fullmatch("src/test/java/com/acme/EditWindowRegressionTest.java")
    assert not JAVA_TEST_PATH.fullmatch("src/main/java/com/acme/EditWindowRegressionTest.java")
    assert not JAVA_TEST_PATH.fullmatch("src/test/java/../../pom.xml")
    assert not JAVA_TEST_PATH.fullmatch("src/test/java/com/acme/Helper.java")


def test_java_regression_tool_rejects_bad_input(tmp_path):
    inv = Investigation("x", java_project(tmp_path), client=object(), model="fake", isolation="process", app=None, kind="maven")
    with Sandbox(inv.source, isolation="process", app=None, kind="maven") as sb:
        ws = Workspace(sb)
        bad_path = inv._regression_test(ws, {"path": "src/main/java/com/acme/XTest.java", "code": "class XTest { @Test void a() {} }"})
        wrong_class = inv._regression_test(ws, {"path": "src/test/java/com/acme/XTest.java", "code": "class YTest { @Test void a() {} }"})
        existing = inv._regression_test(ws, {"path": "src/test/java/com/acme/ShipServiceTest.java", "code": "class ShipServiceTest { @Test void a() {} }"})
    assert "error" in bad_path and "error" in wrong_class
    assert "already exists" in json.dumps(existing)  # existing tests are ground truth, never overwritten
