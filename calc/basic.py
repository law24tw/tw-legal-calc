"""小算盤：安全算式求值（給 LLM 用，不過機率層）。"""
from __future__ import annotations
import ast, math
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING, getcontext
from .dates import CalcError

getcontext().prec = 34

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b}

def _f(x):  # 函式參數轉 float（供 sqrt 等）
    return float(x)

_FUNCS = {
    "abs": abs, "min": min, "max": max, "sum": lambda *a: sum(a[0]) if len(a) == 1 and isinstance(a[0], (list, tuple)) else sum(a),
    "round": lambda x, n=0: Decimal(x).quantize(Decimal(1).scaleb(-int(n)), rounding=ROUND_HALF_UP),
    "sqrt": lambda x: Decimal(str(math.sqrt(_f(x)))),
    "floor": lambda x: Decimal(math.floor(_f(x))), "ceil": lambda x: Decimal(math.ceil(_f(x))),
}
_MODES = {"half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN, "floor": ROUND_FLOOR, "ceil": ROUND_CEILING}


def _ev(n):
    if isinstance(n, ast.Expression):
        return _ev(n.body)
    if isinstance(n, ast.Constant):
        if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
            raise CalcError(f"不支援的常數：{n.value!r}")
        return Decimal(str(n.value))
    if isinstance(n, ast.UnaryOp):
        v = _ev(n.operand)
        if isinstance(n.op, ast.USub):
            return -v
        if isinstance(n.op, ast.UAdd):
            return v
        raise CalcError("不支援的一元運算")
    if isinstance(n, ast.BinOp):
        op = _BIN.get(type(n.op))
        if not op:
            raise CalcError("不支援的運算子")
        b = _ev(n.right)
        if isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod)) and b == 0:
            raise CalcError("除以零")
        return op(_ev(n.left), b)
    if isinstance(n, ast.Call):
        if not isinstance(n.func, ast.Name) or n.func.id not in _FUNCS:
            raise CalcError("只允許 abs/min/max/sum/round/sqrt/floor/ceil")
        if n.keywords:
            raise CalcError("不支援關鍵字參數")
        return _FUNCS[n.func.id](*[_ev(a) for a in n.args])
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_ev(e) for e in n.elts]
    raise CalcError(f"不支援的語法：{type(n).__name__}")


def evaluate(expr: str, precision: int = 2, round_mode: str = "half_up", **_):
    expr = str(expr).strip().replace("，", ",").replace("（", "(").replace("）", ")")
    expr = expr.replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", "")
    if len(expr) > 2000:
        raise CalcError("算式過長")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CalcError(f"算式語法錯誤：{e}")
    raw = _ev(tree)
    if isinstance(raw, list):
        raise CalcError("算式結果不是數值")
    if round_mode == "none":
        val = raw
    else:
        m = _MODES.get(round_mode)
        if not m:
            raise CalcError("round_mode 需為 half_up/half_even/floor/ceil/none")
        val = raw.quantize(Decimal(1).scaleb(-int(precision)), rounding=m)
    return {"expr": expr, "value": float(val), "value_str": str(val), "raw": str(raw),
            "precision": precision, "round_mode": round_mode}
