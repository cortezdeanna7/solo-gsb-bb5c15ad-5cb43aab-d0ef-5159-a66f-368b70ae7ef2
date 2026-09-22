"""SI 单位、词头与量纲定义。

量纲向量固定为 7 元组，顺序：L 长度, M 质量, T 时间, I 电流,
Θ 热力学温度, N 物质的量, J 发光强度。每个分量是 Fraction，
以支持分数幂（如 m^0.5）。
"""
from __future__ import annotations

import math
from fractions import Fraction

DIMLESS = (Fraction(0),) * 7

DIM_SYMBOLS = ["L", "M", "T", "I", "Θ", "N", "J"]
BASE_UNITS = ["m", "kg", "s", "A", "K", "mol", "cd"]


def _dims(L=0, M=0, T=0, I=0, Th=0, N=0, J=0):
    return tuple(Fraction(x) for x in (L, M, T, I, Th, N, J))


class UnitError(Exception):
    """单位解析错误，pos 为输入字符串中的字符位置。"""

    def __init__(self, message: str, pos: int | None = None):
        super().__init__(message)
        self.message = message
        self.pos = pos


# SI 词头（倍率）
PREFIXES = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12,
    "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "da": 1e1,
    "d": 1e-1, "c": 1e-2, "m": 1e-3,
    "u": 1e-6, "µ": 1e-6, "μ": 1e-6,   # 微（两种 Unicode 写法 + u）
    "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24,
}

# 单位符号 -> (换算到 SI 的因子, 量纲向量)
UNITS: dict[str, tuple[float, tuple]] = {
    # SI 基本单位
    "m":   (1.0, _dims(L=1)),
    "kg":  (1.0, _dims(M=1)),
    "g":   (1e-3, _dims(M=1)),
    "s":   (1.0, _dims(T=1)),
    "A":   (1.0, _dims(I=1)),
    "K":   (1.0, _dims(Th=1)),
    "mol": (1.0, _dims(N=1)),
    "cd":  (1.0, _dims(J=1)),
    # 无量纲
    "rad": (1.0, DIMLESS),
    "sr":  (1.0, DIMLESS),
    "deg": (math.pi / 180.0, DIMLESS),
    "%":   (1e-2, DIMLESS),
    "ppm": (1e-6, DIMLESS),
    "ppb": (1e-9, DIMLESS),
    # 常用时间
    "min": (60.0, _dims(T=1)),
    "h":   (3600.0, _dims(T=1)),
    "d":   (86400.0, _dims(T=1)),
    # 体积 / 质量
    "L":   (1e-3, _dims(L=3)),
    "l":   (1e-3, _dims(L=3)),
    "t":   (1e3, _dims(M=1)),
    # SI 导出单位
    "Hz":  (1.0, _dims(T=-1)),
    "N":   (1.0, _dims(L=1, M=1, T=-2)),
    "Pa":  (1.0, _dims(L=-1, M=1, T=-2)),
    "J":   (1.0, _dims(L=2, M=1, T=-2)),
    "W":   (1.0, _dims(L=2, M=1, T=-3)),
    "C":   (1.0, _dims(T=1, I=1)),
    "V":   (1.0, _dims(L=2, M=1, T=-3, I=-1)),
    "F":   (1.0, _dims(L=-2, M=-1, T=4, I=2)),
    "ohm": (1.0, _dims(L=2, M=1, T=-3, I=-2)),
    "Ω":   (1.0, _dims(L=2, M=1, T=-3, I=-2)),
    "S":   (1.0, _dims(L=-2, M=-1, T=3, I=2)),
    "Wb":  (1.0, _dims(L=2, M=1, T=-2, I=-1)),
    "T":   (1.0, _dims(M=1, T=-2, I=-1)),
    "H":   (1.0, _dims(L=2, M=1, T=-2, I=-2)),
    "lm":  (1.0, _dims(J=1)),
    "lx":  (1.0, _dims(L=-2, J=1)),
    "Bq":  (1.0, _dims(T=-1)),
    "Gy":  (1.0, _dims(L=2, T=-2)),
    "Sv":  (1.0, _dims(L=2, T=-2)),
    "kat": (1.0, _dims(T=-1, N=1)),
    # 其他常用单位
    "Wh":  (3600.0, _dims(L=2, M=1, T=-2)),
    "eV":  (1.602176634e-19, _dims(L=2, M=1, T=-2)),
    "cal": (4.184, _dims(L=2, M=1, T=-2)),
    "bar": (1e5, _dims(L=-1, M=1, T=-2)),
    "atm": (101325.0, _dims(L=-1, M=1, T=-2)),
    "psi": (6894.757293168, _dims(L=-1, M=1, T=-2)),
    "in":  (0.0254, _dims(L=1)),
    "ft":  (0.3048, _dims(L=1)),
    "lb":  (0.45359237, _dims(M=1)),
    "mi":  (1609.344, _dims(L=1)),
}

# 量纲向量 -> 导出单位符号（用于结果的美化显示，按优先级匹配）
_DERIVED = [
    (_dims(T=-1), "Hz"),
    (_dims(L=1, M=1, T=-2), "N"),
    (_dims(L=-1, M=1, T=-2), "Pa"),
    (_dims(L=2, M=1, T=-2), "J"),
    (_dims(L=2, M=1, T=-3), "W"),
    (_dims(T=1, I=1), "C"),
    (_dims(L=2, M=1, T=-3, I=-1), "V"),
    (_dims(L=-2, M=-1, T=4, I=2), "F"),
    (_dims(L=2, M=1, T=-3, I=-2), "Ω"),
    (_dims(L=-2, M=-1, T=3, I=2), "S"),
    (_dims(L=2, M=1, T=-2, I=-1), "Wb"),
    (_dims(M=1, T=-2, I=-1), "T"),
    (_dims(L=2, M=1, T=-2, I=-2), "H"),
    (_dims(J=1), "lm"),
    (_dims(L=-2, J=1), "lx"),
    (_dims(L=2, T=-2), "Gy"),
    (_dims(T=-1, N=1), "kat"),
]

_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def sup(n: int) -> str:
    """整数转为上标字符串，如 -2 -> ⁻²。"""
    return str(n).translate(_SUPERSCRIPT)


def _fmt_exp(e: Fraction) -> str:
    if e == 1:
        return ""
    if e.denominator == 1:
        return sup(e.numerator)
    return f"^({e.numerator}/{e.denominator})"


def lookup_unit(symbol: str, pos: int | None = None) -> tuple[float, tuple]:
    """查找单位符号，支持 SI 词头前缀（如 km、mJ、µm）。"""
    if symbol in UNITS:
        return UNITS[symbol]
    # 词头 + 单位：先尝试两字符词头（da），再尝试单字符词头
    for plen in (2, 1):
        if len(symbol) > plen:
            prefix, rest = symbol[:plen], symbol[plen:]
            if prefix in PREFIXES and rest in UNITS:
                factor, dim = UNITS[rest]
                return PREFIXES[prefix] * factor, dim
    hint = "（多个单位请用 · 或空格分隔，如 kg·m/s^2）" if len(symbol) > 1 else ""
    raise UnitError(f"未知单位 '{symbol}'{hint}", pos)


def dim_add(a: tuple, b: tuple) -> tuple:
    return tuple(x + y for x, y in zip(a, b))


def dim_sub(a: tuple, b: tuple) -> tuple:
    return tuple(x - y for x, y in zip(a, b))


def dim_scale(a: tuple, e: Fraction) -> tuple:
    return tuple(x * e for x in a)


def unit_string(dim: tuple) -> str:
    """由量纲向量生成单位显示字符串，优先匹配导出单位。"""
    if dim == DIMLESS:
        return "1"
    for d, name in _DERIVED:
        if d == dim:
            return name
    parts = [sym + _fmt_exp(e) for sym, e in zip(BASE_UNITS, dim) if e]
    return "·".join(parts)


def dim_string(dim: tuple) -> str:
    """量纲的可读字符串，如 L·M·T⁻²；无量纲返回 '无量纲'。"""
    if dim == DIMLESS:
        return "无量纲"
    parts = [sym + _fmt_exp(e) for sym, e in zip(DIM_SYMBOLS, dim) if e]
    return "·".join(parts)
