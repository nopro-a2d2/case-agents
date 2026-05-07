"""Unit tests for CalculateTool — Python sandbox calculator."""

from __future__ import annotations

import json

import pytest

from case_agent.tools.calculate import CalculateTool


@pytest.fixture
def tool() -> CalculateTool:
    return CalculateTool()


def run(tool: CalculateTool, code: str) -> dict:
    return json.loads(tool._run(code))


class TestBasicArithmetic:
    def test_simple_expression(self, tool):
        r = run(tool, "2 + 3 * 4")
        assert r["result"] == 14
        assert r["error"] is None

    def test_float_division(self, tool):
        r = run(tool, "10 / 3")
        assert abs(r["result"] - 3.333333) < 0.001

    def test_assignment_then_expression(self, tool):
        r = run(tool, "x = 100\ny = 30\nx - y")
        assert r["result"] == 70

    def test_explicit_result(self, tool):
        r = run(tool, "_result = 42")
        assert r["result"] == 42


class TestMathModule:
    def test_sqrt(self, tool):
        r = run(tool, "math.sqrt(144)")
        assert r["result"] == 12.0

    def test_log(self, tool):
        r = run(tool, "round(math.log(math.e), 6)")
        assert r["result"] == 1.0

    def test_statistics_mean(self, tool):
        r = run(tool, "statistics.mean([10, 20, 30])")
        assert r["result"] == 20


class TestPrintCapture:
    def test_print_output_captured(self, tool):
        r = run(tool, "print(100 / 3)")
        assert "33.33" in r["stdout"]

    def test_multiline_print(self, tool):
        r = run(tool, "print('a')\nprint('b')")
        assert "a" in r["stdout"]
        assert "b" in r["stdout"]


class TestSecurity:
    def test_import_blocked(self, tool):
        r = run(tool, "import os")
        assert r["error"] is not None
        assert r["result"] is None

    def test_from_import_blocked(self, tool):
        r = run(tool, "from os import path")
        assert r["error"] is not None

    def test_dunder_import_blocked(self, tool):
        r = run(tool, "__import__('os')")
        assert r["error"] is not None

    def test_open_blocked(self, tool):
        r = run(tool, "open('/etc/passwd')")
        assert r["error"] is not None

    def test_os_name_blocked(self, tool):
        r = run(tool, "x = os")
        assert r["error"] is not None


class TestEvalCases:
    def test_ev_ebitda(self, tool):
        code = (
            "ebitda = 10  # json/감정평가.json#p5\n"
            "multiple = 7.2\n"
            "_result = ebitda * multiple"
        )
        r = run(tool, code)
        assert r["result"] == pytest.approx(72.0)

    def test_damage_calc(self, tool):
        code = (
            "acquisition_price = 212  # 억원\n"
            "fair_value = 62          # 상증법 보충평가\n"
            "_result = acquisition_price - fair_value"
        )
        r = run(tool, code)
        assert r["result"] == 150

    def test_wacc(self, tool):
        code = (
            "equity_ratio = 0.6\n"
            "debt_ratio = 0.4\n"
            "cost_of_equity = 0.12\n"
            "cost_of_debt = 0.05\n"
            "tax_rate = 0.25\n"
            "_result = equity_ratio * cost_of_equity + debt_ratio * cost_of_debt * (1 - tax_rate)"
        )
        r = run(tool, code)
        assert r["result"] == pytest.approx(0.087)


class TestErrorHandling:
    def test_zero_division(self, tool):
        r = run(tool, "1 / 0")
        assert r["error"] is not None
        assert "division" in r["error"].lower() or "zero" in r["error"].lower()

    def test_syntax_error(self, tool):
        r = run(tool, "def :")
        assert r["error"] is not None

    def test_empty_code(self, tool):
        r = run(tool, "")
        assert r["error"] is None
        assert r["result"] is None

    def test_undefined_variable(self, tool):
        r = run(tool, "x + 1")
        assert r["error"] is not None
