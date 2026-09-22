"""表达式解析、单位换算与一阶误差传播。

输入语法：
    表达式 [to 目标单位]
    值       := 数字 [± 不确定度[%]] [单位表达式] | ( 表达式 ) [单位表达式] | 单位表达式
    运算符   := + - * / ^ （** 同 ^，· 同 *，支持上标 ² ⁻¹ 等）
    单位     := 符号[^幂] 的乘除组合，支持 SI 词头，如 kg·m/s^2、km/h、mJ

示例：
    2.5±0.1 km/h * 3.0±0.1 h to km
    (4.0±0.1 m)^2
    1 kWh to J
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from .units import (BASE_UNITS, DIMLESS, DIM_SYMBOLS, UnitError, dim_add,
                    dim_scale, dim_string, dim_sub, lookup_unit, sup,
                    unit_string)

# ---------------------------------------------------------------- 错误类型


class EvalError(Exception):
    """求值错误，携带字段名与字符位置，用于字段级错误提示。"""

    def __init__(self, message: str, pos: int | None = None,
                 field: str = "expression"):
        super().__init__(message)
        self.message = message
        self.pos = pos
        self.field = field


# ---------------------------------------------------------------- 词法分析


@dataclass
class Tok:
    kind: str            # 'num' | 'sym' | 'op' | 'pm' | 'arrow'
    text: str
    pos: int
    num: float | None = None


_SUPER_IN = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
             "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+"}
_NUM_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c.isascii() and c.isdigit() or (c == "." and i + 1 < n
                                           and text[i + 1].isdigit()):
            m = _NUM_RE.match(text, i)
            s = m.group(0)
            toks.append(Tok("num", s, i, float(s)))
            i = m.end()
            continue
        if c == "±":
            toks.append(Tok("pm", c, i))
            i += 1
            continue
        if c in "+-*/^()":
            if c == "*" and i + 1 < n and text[i + 1] == "*":
                toks.append(Tok("op", "^", i))
                i += 2
                continue
            if c == "-" and i + 1 < n and text[i + 1] == ">":
                toks.append(Tok("arrow", "->", i))
                i += 2
                continue
            toks.append(Tok("op", c, i))
            i += 1
            continue
        if c in "·•×":
            toks.append(Tok("op", "*", i))
            i += 1
            continue
        if c in _SUPER_IN:
            j = i
            s = ""
            while j < n and text[j] in _SUPER_IN:
                s += _SUPER_IN[text[j]]
                j += 1
            toks.append(Tok("op", "^", i))
            toks.append(Tok("num", s, i, float(s)))
            i = j
            continue
        if c.isalpha() or c in "%µμΩ":
            j = i
            while j < n and (text[j].isalpha() or text[j] in "%µμΩ"):
                j += 1
            toks.append(Tok("sym", text[i:j], i))
            i = j
            continue
        raise EvalError(f"无法识别的字符 '{c}'", i)
    return toks


# ---------------------------------------------------------------- 量与运算


@dataclass
class Quantity:
    value: float
    unc: float
    dim: tuple = DIMLESS


def qmul(a: Quantity, b: Quantity) -> Quantity:
    # σ_f² = (b·σ_a)² + (a·σ_b)²
    unc = math.hypot(b.value * a.unc, a.value * b.unc)
    return Quantity(a.value * b.value, unc, dim_add(a.dim, b.dim))


def qdiv(a: Quantity, b: Quantity, pos: int | None) -> Quantity:
    if b.value == 0:
        raise EvalError("除数为零", pos)
    # σ_f² = (σ_a/b)² + (a·σ_b/b²)²
    unc = math.hypot(a.unc / b.value, a.value * b.unc / b.value ** 2)
    return Quantity(a.value / b.value, unc, dim_sub(a.dim, b.dim))


def qaddsub(a: Quantity, b: Quantity, sign: int, pos: int | None) -> Quantity:
    if a.dim != b.dim:
        raise EvalError(
            f"量纲不兼容：{dim_string(a.dim)} 与 {dim_string(b.dim)} 不能相加减",
            pos)
    return Quantity(a.value + sign * b.value,
                    math.hypot(a.unc, b.unc), a.dim)


def qpow(base: Quantity, exp: Quantity, pos: int | None) -> Quantity:
    if exp.dim != DIMLESS:
        raise EvalError(
            f"非法指数：指数必须是无量纲数，而它的量纲是 {dim_string(exp.dim)}",
            pos)
    n, x = exp.value, base.value
    if x < 0 and not float(n).is_integer():
        raise EvalError("非法指数：负数不能取非整数次幂", pos)
    if x == 0 and n <= 0:
        raise EvalError("非法指数：0 不能取非正数次幂（相当于除数为零）", pos)
    if exp.unc and x <= 0:
        raise EvalError("非法指数：带不确定度的指数要求底数为正", pos)
    try:
        val = x ** n
    except OverflowError:
        val = math.inf
    # 一阶误差传播：σ_f² = (n·x^(n-1)·σ_x)² + (x^n·ln x·σ_n)²
    if x == 0:
        if base.unc and n < 1:
            raise EvalError("不确定度在该点不可传播（导数发散）", pos)
        d1 = 1.0 if n == 1 else 0.0
    else:
        d1 = n * x ** (n - 1)
    s2 = abs(val * math.log(x)) * exp.unc if exp.unc else 0.0
    unc = math.hypot(abs(d1) * base.unc, s2)
    nf = Fraction(str(n)).limit_denominator(10 ** 6)
    return Quantity(val, unc, dim_scale(base.dim, nf))


# ---------------------------------------------------------------- 语法分析


class Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = tokenize(text)
        self.i = 0

    def peek(self, k: int = 0) -> Tok | None:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    # -- 入口：表达式 [to 单位] --
    def parse(self) -> tuple[Quantity, tuple[float, tuple, str] | None]:
        if not self.toks:
            raise EvalError("表达式为空", 0)
        q = self.parse_sum()
        target = None
        tok = self.peek()
        if tok and (tok.kind == "arrow"
                    or (tok.kind == "sym" and tok.text == "to")):
            self.i += 1
            t0 = self.peek()
            if t0 is None:
                raise EvalError("'to' 之后缺少目标单位", tok.pos)
            factor, dim = self.parse_unit()
            rest = self.peek()
            if rest is not None:
                raise EvalError(f"目标单位之后有多余内容 '{rest.text}'", rest.pos)
            target = (factor, dim, self.text[t0.pos:].strip())
        elif tok is not None:
            raise EvalError(f"此处出现意外的 '{tok.text}'", tok.pos)
        return q, target

    # -- 加减 --
    def parse_sum(self) -> Quantity:
        left = self.parse_product()
        while True:
            tok = self.peek()
            if tok and tok.kind == "op" and tok.text in "+-":
                self.i += 1
                right = self.parse_product()
                left = qaddsub(left, right, 1 if tok.text == "+" else -1,
                               tok.pos)
            else:
                return left

    # -- 乘除 --
    def parse_product(self) -> Quantity:
        left = self.parse_unary()
        while True:
            tok = self.peek()
            if tok and tok.kind == "op" and tok.text == "*":
                self.i += 1
                left = qmul(left, self.parse_unary())
            elif tok and tok.kind == "op" and tok.text == "/":
                self.i += 1
                left = qdiv(left, self.parse_unary(), tok.pos)
            else:
                return left

    # -- 一元正负号 --
    def parse_unary(self) -> Quantity:
        tok = self.peek()
        if tok and tok.kind == "op" and tok.text == "-":
            self.i += 1
            q = self.parse_unary()
            return Quantity(-q.value, q.unc, q.dim)
        if tok and tok.kind == "op" and tok.text == "+":
            self.i += 1
            return self.parse_unary()
        return self.parse_power()

    # -- 幂（右结合） --
    def parse_power(self) -> Quantity:
        base = self.parse_postfix()
        tok = self.peek()
        if tok and tok.kind == "op" and tok.text == "^":
            self.i += 1
            return qpow(base, self.parse_unary(), tok.pos)
        return base

    # -- 后缀单位：数字或括号组之后可直接跟单位表达式 --
    def parse_postfix(self) -> Quantity:
        q = self.parse_atom()
        tok = self.peek()
        if tok and ((tok.kind == "sym" and tok.text != "to")
                    or (tok.kind == "op" and tok.text == "(")
                    or (tok.kind == "num" and tok.num == 1.0)):
            save = self.i
            try:
                factor, dim = self.parse_unit()
            except EvalError:
                if tok.kind == "op":   # '(' 不是单位（如 "2 (3+4)"），回退
                    self.i = save
                    return q
                raise
            q = qmul(q, Quantity(factor, 0.0, dim))
        return q

    # -- 原子：数字[±不确定度] / (表达式) / 独立单位 --
    def parse_atom(self) -> Quantity:
        tok = self.peek()
        if tok is None:
            raise EvalError("表达式意外结束", len(self.text))
        if tok.kind == "num":
            self.i += 1
            value, unc = tok.num, 0.0
            t = self.peek()
            if t and t.kind == "pm":
                self.i += 1
                u = self.peek()
                if not (u and u.kind == "num"):
                    raise EvalError("'±' 之后应是不确定度数值", t.pos)
                self.i += 1
                unc = u.num
                pct = self.peek()
                if pct and pct.kind == "sym" and pct.text == "%":
                    self.i += 1
                    unc = abs(value) * unc / 100.0
            return Quantity(value, unc, DIMLESS)
        if tok.kind == "op" and tok.text == "(":
            self.i += 1
            q = self.parse_sum()
            t = self.peek()
            if not (t and t.kind == "op" and t.text == ")"):
                raise EvalError("括号未闭合，缺少 ')'", tok.pos)
            self.i += 1
            return q
        if tok.kind == "sym" and tok.text != "to":
            factor, dim = self.parse_unit()   # 独立单位，如 "m/s" 表示 1 m/s
            return Quantity(factor, 0.0, dim)
        raise EvalError(f"此处应有数字、括号或单位，而不是 '{tok.text}'",
                        tok.pos)

    # -- 单位表达式：符号[^幂] 的乘除组合，支持隐式乘法 --
    def parse_unit(self) -> tuple[float, tuple]:
        factor, dim = 1.0, DIMLESS
        started = False
        pending = "*"
        while True:
            tok = self.peek()
            if tok is None:
                break
            if tok.kind == "sym" and tok.text != "to":
                try:
                    f, d = lookup_unit(tok.text, tok.pos)
                except UnitError as e:
                    raise EvalError(e.message, e.pos)
                self.i += 1
                e = self.maybe_power()
                f, d = f ** float(e), dim_scale(d, e)
            elif tok.kind == "num" and tok.num == 1.0:
                f, d = 1.0, DIMLESS   # 允许 "1/mol" 这类写法
                self.i += 1
            elif tok.kind == "op" and tok.text == "(":
                self.i += 1
                f, d = self.parse_unit()
                t2 = self.peek()
                if not (t2 and t2.kind == "op" and t2.text == ")"):
                    raise EvalError("单位括号未闭合，缺少 ')'", tok.pos)
                self.i += 1
                e = self.maybe_power()
                f, d = f ** float(e), dim_scale(d, e)
            else:
                if not started:
                    raise EvalError(f"此处应有单位符号，而不是 '{tok.text}'",
                                    tok.pos)
                break
            started = True
            if pending == "*":
                factor, dim = factor * f, dim_add(dim, d)
            else:
                factor, dim = factor / f, dim_sub(dim, d)
            # 连接符：显式 */ 或隐式（下一个符号/左括号即相乘）
            tok = self.peek()
            if tok and tok.kind == "op" and tok.text in "*/":
                nt = self.peek(1)
                if nt and ((nt.kind == "sym" and nt.text != "to")
                           or (nt.kind == "op" and nt.text == "(")):
                    pending = tok.text
                    self.i += 1
                    continue
                break
            if tok and ((tok.kind == "sym" and tok.text != "to")
                        or (tok.kind == "op" and tok.text == "(")):
                pending = "*"
                continue
            break
        if not started:
            pos = self.toks[self.i].pos if self.i < len(self.toks) \
                else len(self.text)
            raise EvalError("此处应有单位符号", pos)
        return factor, dim

    def maybe_power(self) -> Fraction:
        tok = self.peek()
        if tok and tok.kind == "op" and tok.text == "^":
            self.i += 1
            sign = 1
            t = self.peek()
            if t and t.kind == "op" and t.text in "+-":
                sign = -1 if t.text == "-" else 1
                self.i += 1
            t = self.peek()
            if t and t.kind == "num":
                self.i += 1
                try:
                    return Fraction(t.text) * sign
                except ValueError:
                    return Fraction(t.num).limit_denominator(10 ** 6) * sign
            raise EvalError("'^' 之后应为数字指数", tok.pos)
        return Fraction(1)


# ---------------------------------------------------------------- 结果格式化


def _fmt_plain(x: float) -> str:
    if x == 0:
        return "0"
    if not math.isfinite(x):
        return "∞" if x > 0 else "-∞"
    if 1e-4 <= abs(x) < 1e7:
        return f"{x:.6f}".rstrip("0").rstrip(".")
    mant, exp = f"{x:.5e}".split("e")
    return f"{mant}×10{sup(int(exp))}"


def format_quantity(value: float, unc: float, unit: str) -> str:
    """按不确定度对齐有效数字：不确定度保留两位，值对齐到同一小数位。"""
    u = f" {unit}" if unit and unit != "1" else ""
    if unc == 0:
        return f"{_fmt_plain(value)}{u}"
    if not (math.isfinite(value) and math.isfinite(unc)):
        return f"{_fmt_plain(value)} ± {_fmt_plain(unc)}{u}"
    e = int(math.floor(math.log10(abs(unc))))
    nd = 1 - e
    if -6 <= e <= 9:
        vr, ur = round(value, nd), round(unc, nd)
        fmt = f"{{:.{max(nd, 0)}f}}"
        return f"{fmt.format(vr)} ± {fmt.format(ur)}{u}"
    big = int(math.floor(math.log10(abs(value)))) if value != 0 else e
    nd2 = max(0, 1 - (e - big))
    return (f"({value / 10 ** big:.{nd2}f} ± {unc / 10 ** big:.{nd2}f})"
            f"×10{sup(big)}{u}")


def _safe(x: float):
    """JSON 不支持 Infinity/NaN，转为字符串。"""
    if isinstance(x, float) and not math.isfinite(x):
        return "∞" if x > 0 else ("-∞" if x < 0 else "NaN")
    return x


# ---------------------------------------------------------------- 对外入口


def evaluate(text: str) -> dict:
    """求值表达式，返回结果字典；出错抛 EvalError。"""
    q, target = Parser(text).parse()
    si_unit = unit_string(q.dim)
    if target is not None:
        factor, dim, disp = target
        if dim != q.dim:
            raise EvalError(
                f"量纲不匹配：结果量纲为 {dim_string(q.dim)}，"
                f"无法换算成 '{disp}'（量纲 {dim_string(dim)}）")
        value, unc, unit = q.value / factor, q.unc / factor, disp
    else:
        value, unc, unit = q.value, q.unc, si_unit
    rel = unc / abs(value) if value else None
    return {
        "value": _safe(value),
        "uncertainty": _safe(unc),
        "unit": unit,
        "formatted": format_quantity(value, unc, unit),
        "relative_uncertainty": _safe(rel) if rel is not None else None,
        "si": {
            "value": _safe(q.value),
            "uncertainty": _safe(q.unc),
            "unit": si_unit,
            "formatted": format_quantity(q.value, q.unc, si_unit),
        },
        "dimension": dim_string(q.dim),
    }
