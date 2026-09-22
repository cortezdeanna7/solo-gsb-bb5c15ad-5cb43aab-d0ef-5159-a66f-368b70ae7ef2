"""重复测量合并：逐行解析测量值，统一量纲后按逆方差加权平均。

每行格式：值[±不确定度[%]] [单位]（复用表达式解析器，支持 SI 词头）。
合并规则：
  - 所有行换算到 SI 后量纲必须一致，否则逐行报错；
  - 无不确定度（σ = 0）的行视为精确值：
      * 全部精确值互相一致 → 直接作为结果（σ = 0）；
      * 多个精确值互相矛盾 → 逐行报错；
  - 否则按逆方差权重 w_i = 1/σ_i² 加权平均，
    合成不确定度 σ = 1/√Σw_i。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .evaluator import EvalError, Parser, _safe, format_quantity
from .units import dim_string, unit_string

# 精确值一致性判定的相对容差（吸收浮点换算误差，如 30 cm 与 0.3 m）
_EXACT_TOL = 1e-9


@dataclass
class Row:
    line: int       # 行号（从 1 开始）
    text: str       # 原始输入
    value: float    # SI 值
    unc: float      # SI 不确定度，0 表示精确值
    dim: tuple      # 量纲向量


def _err(message: str, line: int | None = None, pos: int | None = None,
         field: str | None = None) -> dict:
    return {"line": line, "field": field, "message": message, "position": pos}


def _same(a: float, b: float) -> bool:
    """判断两个精确值是否一致（允许浮点换算误差）。"""
    return a == b or abs(a - b) <= _EXACT_TOL * max(abs(a), abs(b))


def _parse_target_unit(text: str) -> tuple[float, tuple]:
    """解析输出单位表达式，要求完整消耗输入。"""
    p = Parser(text)
    factor, dim = p.parse_unit()
    tok = p.peek()
    if tok is not None:
        raise EvalError(f"目标单位之后有多余内容 '{tok.text}'", tok.pos)
    return factor, dim


def _parse_rows(text: str) -> tuple[list[Row], list[dict]]:
    """逐行解析，空行跳过；返回 (有效行, 逐行错误)。"""
    rows, errors = [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            q, target = Parser(line).parse()
        except EvalError as e:
            errors.append(_err(e.message, line=lineno, pos=e.pos))
            continue
        if target is not None:
            errors.append(_err("行内不需要 'to' 换算，输出单位请统一指定",
                               line=lineno))
            continue
        rows.append(Row(lineno, line, q.value, q.unc, q.dim))
    return rows, errors


def aggregate(text: str, unit: str = "") -> dict:
    """合并多行测量值，返回 API 响应字典（含 ok 标志）。"""
    errors: list[dict] = []

    # 输出单位（留空则结果以 SI 单位表示）
    factor, udim = 1.0, None
    unit = unit.strip()
    if unit:
        try:
            factor, udim = _parse_target_unit(unit)
        except EvalError as e:
            errors.append(_err(e.message, pos=e.pos, field="unit"))

    # 逐行解析
    rows, row_errors = _parse_rows(text)
    errors.extend(row_errors)
    if errors:
        return {"ok": False, "errors": errors}
    if not rows:
        return {"ok": False,
                "errors": [_err("请至少输入一行测量值", field="lines")]}

    # 量纲一致性（以第一行为基准）
    dim0 = rows[0].dim
    for r in rows[1:]:
        if r.dim != dim0:
            errors.append(_err(
                f"量纲不符：本行量纲为 {dim_string(r.dim)}，"
                f"与第 {rows[0].line} 行（{dim_string(dim0)}）不一致",
                line=r.line))
    if errors:
        return {"ok": False, "errors": errors}

    # 输出单位量纲校验
    if udim is not None and udim != dim0:
        return {"ok": False, "errors": [_err(
            f"输出单位量纲不符：测量值量纲为 {dim_string(dim0)}，"
            f"无法以 '{unit}'（量纲 {dim_string(udim)}）表示", field="unit")]}

    # 合并：精确值优先，否则逆方差加权
    exacts = [r for r in rows if r.unc == 0]
    weights: list[float | None] = [None] * len(rows)
    if exacts:
        for r in exacts:
            other = next((o for o in exacts if o is not r
                          and not _same(o.value, r.value)), None)
            if other is not None:
                errors.append(_err(
                    f"精确值互相矛盾：本行（{r.text}）与"
                    f"第 {other.line} 行（{other.text}）不一致",
                    line=r.line))
        if errors:
            return {"ok": False, "errors": errors}
        si_value, si_unc, method = exacts[0].value, 0.0, "exact"
    else:
        # 用相对权重（以最小 σ 归一）避免 1/σ² 溢出，数学上等价
        sig_min = min(r.unc for r in rows)
        for i, r in enumerate(rows):
            weights[i] = (sig_min / r.unc) ** 2
        wsum = math.fsum(w for w in weights if w is not None)
        si_value = math.fsum(w * r.value for w, r in zip(weights, rows)
                             if w is not None) / wsum
        si_unc = sig_min / math.sqrt(wsum)
        method = "weighted"

    # 结果（换算到输出单位）
    si_unit = unit_string(dim0)
    disp = unit or si_unit
    value, unc = si_value / factor, si_unc / factor
    rel = unc / abs(value) if value else None
    out_rows = []
    for r, w in zip(rows, weights):
        out_rows.append({
            "line": r.line,
            "input": r.text,
            "value": _safe(r.value / factor),
            "uncertainty": _safe(r.unc / factor),
            "formatted": format_quantity(r.value / factor, r.unc / factor,
                                         disp),
            "exact": r.unc == 0,
            "weight": _safe(w) if w is not None else None,
        })
    result = {
        "value": _safe(value),
        "uncertainty": _safe(unc),
        "unit": disp,
        "formatted": format_quantity(value, unc, disp),
        "relative_uncertainty": _safe(rel) if rel is not None else None,
        "si": {
            "value": _safe(si_value),
            "uncertainty": _safe(si_unc),
            "unit": si_unit,
            "formatted": format_quantity(si_value, si_unc, si_unit),
        },
        "dimension": dim_string(dim0),
        "method": method,
        "count": len(rows),
    }
    return {"ok": True, "result": result, "rows": out_rows}
