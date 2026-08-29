"""Arithmetic that is computed rather than generated.

A worked numerical is the one place a language model's confident fluency is
actively dangerous: "u = 20, theta = 35 degrees, so R = 38.4 m" reads exactly
as well when the number is wrong, and a student checking their homework
against it has no way to tell.

WHY NOT ADK's CODE EXECUTOR. `BuiltInCodeExecutor` runs on Google's side but
cannot be combined with function declarations on Gemini, and BoardAgent is
nothing but function declarations. `UnsafeLocalCodeExecutor` does what its
name says. Neither trade is worth making for arithmetic.

So this evaluates an expression through Python's own parser and walks the AST,
allowing only what arithmetic needs. There is no eval(), no builtins, no
attribute access, no names except the handful of maths functions below — a
malformed or hostile expression is a rejection, not an exception and not a
shell.
"""
from __future__ import annotations

import ast
import math
import operator

_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# Degrees, deliberately: Class 11 projectile questions are stated in degrees,
# and radian/degree confusion is the single likeliest way to get a right
# method and a wrong number.
_NAMES = {
    "pi": math.pi, "e": math.e, "g": 9.8,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "log": math.log, "log10": math.log10, "exp": math.exp,
}

MAX_POWER = 1000
"""`2 ** 10**9` is a denial of service written in four characters."""


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"{node.value!r} is not a number")
    if isinstance(node, ast.BinOp):
        op = _BINARY.get(type(node.op))
        if op is None:
            raise ValueError(f"{type(node.op).__name__} is not allowed")
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
            raise ValueError(f"exponent {right} is too large")
        return op(_eval(node.left), right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY.get(type(node.op))
        if op is None:
            raise ValueError(f"{type(node.op).__name__} is not allowed")
        return op(_eval(node.operand))
    if isinstance(node, ast.Name):
        if node.id in _NAMES and not callable(_NAMES[node.id]):
            return _NAMES[node.id]
        raise ValueError(f"unknown name {node.id!r}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only plain function calls are allowed")
        fn = _NAMES.get(node.func.id)
        if not callable(fn):
            raise ValueError(f"unknown function {node.func.id!r}")
        if node.keywords:
            raise ValueError("keyword arguments are not allowed")
        return fn(*(_eval(a) for a in node.args))
    raise ValueError(f"{type(node).__name__} is not allowed here")


def calculate(expression: str) -> dict:
    """Work out a number. Use this for EVERY arithmetic step you write down.

    Angles are in DEGREES. `g` is 9.8. Available: sin, cos, tan, asin, acos,
    atan, sqrt, log, log10, exp, abs, round, pi, e.

        calculate("20**2 * sin(2*35) / 9.8")   ->  38.36

    Args:
        expression: The arithmetic to evaluate, e.g. "20**2 * sin(90) / 9.8".

    Returns:
        dict with "value" (a number) and "rounded" (2 decimal places), or
        {"error": ...} if the expression is not arithmetic this can do.
    """
    try:
        tree = ast.parse(str(expression), mode="eval")
    except SyntaxError as exc:
        return {"error": f"could not parse {expression!r}: {exc.msg}"}
    try:
        value = _eval(tree)
    except ZeroDivisionError:
        return {"error": "division by zero"}
    except (ValueError, TypeError, OverflowError) as exc:
        return {"error": str(exc)}
    if isinstance(value, complex) or value != value or value in (float("inf"), float("-inf")):
        return {"error": f"{expression!r} is not a real finite number"}
    return {"value": value, "rounded": round(float(value), 2)}
