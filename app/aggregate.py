"""重复测量合并：逐行解析测量值，按逆方差权重计算加权平均。

合并规则：
- 每行是一个测量表达式（值±不确定度 单位），解析后换算到 SI，量纲必须一致；
- 不带 ± 的行视为精确值：单个（或多个互相一致的）精确值直接作为结果（σ = 0）；
  多个互相矛盾的精确值会产生逐行错误；
- 其余情况按逆方差加权：w_i = 1/σ_i²，x̄ = Σw_i·x_i / Σw_i，σ = 1/√Σw_i。
"""
from __future__ import annotations

import math

from .evaluator import EvalError, Parser, _safe, format_quantity
from .units import dim_string, unit_string

# 精确值一致性判定的相对容差（吸收 “250 cm 与 2.5 m” 之类的浮点尾差）
_EXACT_TOL = 1e-9


def _parse_output_unit(text: str) -> tuple[float, tuple]:
    """解析输出单位，要求整串恰好构成一个单位表达式。"""
    p = Parser(text)
    if not p.toks:
        raise EvalError("输出单位不能为空", 0)
    factor, dim = p.parse_unit()
    rest = p.peek()
    if rest is not None:
        raise EvalError(f"输出单位之后有多余内容 '{rest.text}'", rest.pos)
    return factor, dim


def _line_err(no: int, message: str, pos: int | None = None,
              text: str = "") -> dict:
    return {"line": no, "message": message, "position": pos, "text": text}


def aggregate(lines_text: str, unit: str = "") -> dict:
    """合并逐行测量值。

    返回 {"ok": True, "result": ...} 或 {"ok": False, "errors": [...]}；
    行级错误携带 1 起始的行号 line 与该行原文 text。
    """
    unit = (unit or "").strip()
    if unit:
        try:
            factor, dim = _parse_output_unit(unit)
        except EvalError as e:
            return {"ok": False, "errors": [
                {"field": "unit", "message": e.message, "position": e.pos}]}
    else:
        factor, dim = 1.0, None

    # ---- 逐行解析（空行跳过；错误收集后继续，便于一次标出所有问题行）----
    rows: list[dict] = []
    errors: list[dict] = []
    for no, raw in enumerate((lines_text or "").split("\n"), start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            q, target = Parser(text).parse()
        except EvalError as e:
            errors.append(_line_err(no, e.message, e.pos, text))
            continue
        if target is not None:
            errors.append(_line_err(
                no, "行内不需要 'to' 换算，请统一在“输出单位”中指定", text=text))
            continue
        rows.append({"line": no, "text": text, "q": q})
    if errors:
        return {"ok": False, "errors": errors}
    if not rows:
        return {"ok": False, "errors": [
            {"field": "lines", "message": "请至少输入一行测量值",
             "position": None}]}

    # ---- 量纲校验（未指定输出单位时以第一行的量纲为准）----
    if dim is None:
        dim = rows[0]["q"].dim
    errors = [
        _line_err(r["line"],
                  f"量纲不符：应为 {dim_string(dim)}，"
                  f"而该行是 {dim_string(r['q'].dim)}",
                  text=r["text"])
        for r in rows if r["q"].dim != dim]
    if errors:
        return {"ok": False, "errors": errors}

    # ---- 分离精确值与带不确定度的行，预计算权重份额 ----
    exacts = [r for r in rows if r["q"].unc == 0]
    weighted = [r for r in rows if r["q"].unc > 0]
    shares: dict[int, float] = {}
    s_min, sw, ws = 0.0, 0.0, []
    if weighted:
        # 以最小不确定度为基准计算相对权重，避免 1/σ² 上溢/下溢
        s_min = min(r["q"].unc for r in weighted)
        ws = [(s_min / r["q"].unc) ** 2 for r in weighted]
        sw = math.fsum(ws)
        if not (math.isfinite(sw) and sw > 0):
            return {"ok": False, "errors": [
                {"field": "lines",
                 "message": "无法合并：有效权重为零（不确定度异常）",
                 "position": None}]}
        shares = {r["line"]: w / sw for w, r in zip(ws, weighted)}

    # ---- 合并 ----
    if exacts:
        ref = exacts[0]["q"].value
        if any(not math.isclose(r["q"].value, ref,
                                rel_tol=_EXACT_TOL, abs_tol=0.0)
               for r in exacts[1:]):
            unit_out = unit or unit_string(dim)
            return {"ok": False, "errors": [
                _line_err(r["line"],
                          "精确值 "
                          + format_quantity(r["q"].value / factor, 0.0,
                                            unit_out)
                          + " 与其他行的精确值不一致",
                          text=r["text"])
                for r in exacts]}
        value_si, unc_si, method = ref, 0.0, "exact"
    else:
        try:
            value_si = math.fsum(w * r["q"].value
                                 for w, r in zip(ws, weighted)) / sw
        except (OverflowError, ValueError):
            # 含 inf 等极端值时退化为普通求和，结果由 _safe 序列化
            value_si = sum(w * r["q"].value
                           for w, r in zip(ws, weighted)) / sw
        unc_si, method = s_min / math.sqrt(sw), "weighted"

    # ---- 汇总输出 ----
    unit_out = unit or unit_string(dim)
    value, unc = value_si / factor, unc_si / factor
    if unc_si == 0:
        rel = 0.0
    elif value_si:
        rel = unc_si / abs(value_si)
    else:
        rel = None
    si_unit = unit_string(dim)
    return {"ok": True, "result": {
        "value": _safe(value),
        "uncertainty": _safe(unc),
        "unit": unit_out,
        "formatted": format_quantity(value, unc, unit_out),
        "relative_uncertainty": _safe(rel) if rel is not None else None,
        "si": {
            "value": _safe(value_si),
            "uncertainty": _safe(unc_si),
            "unit": si_unit,
            "formatted": format_quantity(value_si, unc_si, si_unit),
        },
        "dimension": dim_string(dim),
        "method": method,
        "row_count": len(rows),
        "exact_count": len(exacts),
        "weighted_count": len(weighted),
        "rows": [{
            "line": r["line"],
            "text": r["text"],
            "value": _safe(r["q"].value / factor),
            "uncertainty": _safe(r["q"].unc / factor),
            "formatted": format_quantity(r["q"].value / factor,
                                         r["q"].unc / factor, unit_out),
            "exact": r["q"].unc == 0,
            "weight_share": shares.get(r["line"]),
        } for r in rows],
    }}
