"""Python sandbox calculator tool.

Provides a restricted Python execution environment for numerical computations.
The agent extracts numbers from case sources first, then calls this tool to
perform calculations. All numbers used should carry inline citations so results
are traceable back to evidence.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import math
import statistics
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel


_ALLOWED_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "sum": sum,
    "min": min,
    "max": max,
    "pow": pow,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "dict": dict,
    "range": range,
    "print": print,
    "len": len,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}

_BLOCKED_NAMES = frozenset({"__import__", "open", "os", "sys", "subprocess", "eval", "exec", "compile", "__builtins__"})


class CalculateInput(BaseModel):
    code: str


class CalculateTool(BaseTool):
    """Python sandbox calculator — runs code in a restricted namespace.

    Usage: extract numbers from case sources, pass them as Python code.
    Always cite the source of each number (e.g. @@[1]) in the code as a
    comment so the calculation is traceable to evidence.

    Example::

        code: |
          ebitda = 10  # @@[감정평가]  (제5쪽)
          multiple = 7.2  # @@[ev-ebitda]
          _result = ebitda * multiple

    Returns JSON: {"result": <value>, "stdout": <print output>, "error": <msg or null>}
    """

    name: str = "calculate"
    description: str = (
        "Python sandbox for numerical computations (math, statistics modules available). "
        "Extract numbers from case sources first, then call this tool. "
        "Annotate each number with its source citation as a comment. "
        "Set _result = <value> to return a specific value, or end with a bare expression. "
        "Returns JSON {result, stdout, error}."
    )
    args_schema: Type[BaseModel] = CalculateInput

    def _run(self, code: str) -> str:
        buf = io.StringIO()
        namespace: dict[str, Any] = {
            "__builtins__": _ALLOWED_BUILTINS,
            "math": math,
            "statistics": statistics,
        }

        try:
            self._check_blocked(code)
            prepared = self._prepare_code(code)
            compiled = compile(prepared, "<calculate>", "exec")
            with contextlib.redirect_stdout(buf):
                exec(compiled, namespace)  # noqa: S102
        except Exception as exc:
            return json.dumps({"result": None, "stdout": buf.getvalue(), "error": str(exc)}, ensure_ascii=False)

        result = namespace.get("_result")
        return json.dumps({"result": result, "stdout": buf.getvalue(), "error": None}, ensure_ascii=False)

    def _check_blocked(self, code: str) -> None:
        """Raise if any blocked name appears in the code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return  # Let exec handle the syntax error
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES:
                raise ValueError(f"'{node.id}' is not allowed in calculate")
            if isinstance(node, ast.Attribute) and node.attr in _BLOCKED_NAMES:
                raise ValueError(f"'.{node.attr}' is not allowed in calculate")
            if isinstance(node, ast.Import | ast.ImportFrom):
                raise ValueError("import statements are not allowed in calculate")

    @staticmethod
    def _prepare_code(code: str) -> str:
        """Wrap the last bare expression as `_result = <expr>` for value capture."""
        lines = code.rstrip().splitlines()
        if not lines:
            return code
        last = lines[-1]
        # Strip inline comments to test if the last line is a bare expression
        stripped = last.split("#")[0].strip()
        if not stripped:
            return code
        try:
            tree = ast.parse(stripped, mode="eval")
            # It's a valid expression — wrap it
            lines[-1] = f"_result = {last}"
            return "\n".join(lines)
        except SyntaxError:
            return code


__all__ = ["CalculateTool"]
