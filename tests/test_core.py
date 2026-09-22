"""核心功能自测：解析、换算、误差传播与三类错误。直接运行：python tests/test_core.py"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.evaluator import EvalError, evaluate  # noqa: E402
from app.aggregate import aggregate  # noqa: E402

PASSED = 0


def check(cond, label):
    global PASSED
    assert cond, f"FAIL: {label}"
    PASSED += 1
    print(f"  ok - {label}")


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def expect_error(expr, keyword):
    try:
        evaluate(expr)
    except EvalError as e:
        check(keyword in e.message, f"'{expr}' 报错含 '{keyword}'（实际：{e.message}）")
        return
    raise AssertionError(f"FAIL: '{expr}' 应报错 '{keyword}' 但却成功了")


# --- 基本解析与换算 ---
r = evaluate("1 km + 500 m to m")
check(close(r["value"], 1500) and r["unit"] == "m", "1 km + 500 m = 1500 m")

r = evaluate("2.5±0.1 km/h * 3.0±0.1 h to km")
check(close(r["value"], 7.5), "2.5 km/h * 3 h = 7.5 km")
check(close(r["uncertainty"], math.hypot(10800 * 0.1 / 3.6, 2.5 / 3.6 * 360) / 1000, 1e-6),
      "乘积的一阶误差传播")
print("    formatted:", r["formatted"])

r = evaluate("9.8±0.05 m/s^2 * 65±0.5 kg")
check(r["unit"] == "N" and close(r["value"], 637.0), "m/s^2 * kg 识别为 N")

r = evaluate("100 mJ to J")
check(close(r["value"], 0.1), "SI 词头 mJ -> J")

r = evaluate("2 µm to nm")
check(close(r["value"], 2000), "µm -> nm")

r = evaluate("1 kWh to J")
check(close(r["value"], 3.6e6), "kWh -> J")

r = evaluate("(4.0±0.1 m)^2 to m^2")
check(close(r["value"], 16.0) and close(r["uncertainty"], 2 * 4.0 * 0.1),
      "幂运算与误差传播 (x^2 -> σ=2xσ)")

r = evaluate("1.5±0.02 V / 0.75±0.01 mA to Ω")
check(close(r["value"], 2000.0) and r["unit"] == "Ω", "V/mA -> Ω")

r = evaluate("500±5 mg + 1.2±0.01 g to g")
check(close(r["value"], 1.7) and close(r["uncertainty"], math.hypot(0.005, 0.01)),
      "加减误差传播（平方和根）")

r = evaluate("2.5±2% V")
check(close(r["uncertainty"], 0.05), "百分比不确定度")

r = evaluate("10 m*s^-2")
check(r["unit"] == "m·s⁻²", "负指数单位显示")

r = evaluate("3 kg m / s^2")
check(r["unit"] == "N" and close(r["value"], 3), "隐式单位乘法 kg m / s^2")

r = evaluate("1 m + 1 s", ) if False else None
# --- 三类字段级错误 ---
expect_error("1 m + 1 s", "量纲不兼容")
expect_error("1 / (2 - 2)", "除数为零")
expect_error("(2 m)^(1 s)", "非法指数")
expect_error("(-2)^0.5", "非法指数")
expect_error("0^0", "非法指数")
expect_error("1 m to s", "量纲不匹配")
expect_error("2 blorp", "未知单位")

# --- 格式化 ---
check(evaluate("2.5±0.1 km to km")["formatted"] == "2.50 ± 0.10 km", "格式化对齐小数位")
check(evaluate("2.5±0.1 km")["formatted"] == "2500 ± 100 m", "无 to 时以 SI 单位表示")
r = evaluate("6.022e23 1/mol")
check(close(r["value"], 6.022e23) and r["unit"] == "mol⁻¹", "1/mol 单位写法")


# --- 重复测量合并 ---
def agg_ok(text, unit=""):
    r = aggregate(text, unit)
    assert r["ok"], f"aggregate 应成功：{r}"
    return r


def agg_err(text, unit=""):
    r = aggregate(text, unit)
    assert not r["ok"], f"aggregate 应失败：{r}"
    return r["errors"]


# 等权重：均值取算术平均，σ = σ_i/√n
r = agg_ok("1.0±0.1 m\n1.2±0.1 m")
check(close(r["result"]["value"], 1.1), "合并：等权重加权平均")
check(close(r["result"]["uncertainty"], 0.1 / math.sqrt(2)),
      "合并：合成不确定度 1/√Σw")
check(r["result"]["method"] == "weighted" and r["result"]["count"] == 2,
      "合并：加权方式与有效行数")

# 逆方差权重：w1:w2 = 4:1
r = agg_ok("1.0±0.1 m\n1.2±0.2 m")
check(close(r["result"]["value"], (1.0 * 4 + 1.2) / 5), "合并：逆方差权重")
check(close(r["result"]["uncertainty"], 1 / math.sqrt(1 / 0.01 + 1 / 0.04)),
      "合并：逆方差合成不确定度")

# 跨单位合并 + 输出单位换算：1000±10 m 与 1020±20 m → 1004 m
r = agg_ok("1.0±0.01 km\n1020±20 m", "m")
check(close(r["result"]["value"], 1004.0) and r["result"]["unit"] == "m",
      "合并：跨单位统一量纲并换算输出单位")
check(close(r["result"]["uncertainty"], 20 / math.sqrt(5)),
      "合并：跨单位合成不确定度")
check(len(r["rows"]) == 2 and r["rows"][0]["line"] == 1
      and close(r["rows"][1]["weight"], 0.25), "合并：有效行与相对权重")

# 输出单位为 km
r = agg_ok("1500±10 m\n1600±10 m", "km")
check(close(r["result"]["value"], 1.55) and r["result"]["unit"] == "km",
      "合并：结果换算到 km")
check(close(r["result"]["relative_uncertainty"],
            (0.1 / math.sqrt(2)) / 15.5, 1e-6), "合并：相对不确定度")

# 空行跳过
r = agg_ok("\n1.0±0.1 m\n\n1.2±0.1 m\n")
check(r["result"]["count"] == 2, "合并：空行自动跳过")

# 单个精确值直接作为结果
r = agg_ok("1.5 m\n1.5±0.2 m\n1.6±0.3 m")
check(r["result"]["method"] == "exact" and close(r["result"]["value"], 1.5)
      and r["result"]["uncertainty"] == 0, "合并：单个精确值直接作为结果")

# 多个一致精确值（跨单位、浮点换算误差内容差）
r = agg_ok("0.3 m\n30 cm")
check(r["result"]["method"] == "exact" and close(r["result"]["value"], 0.3),
      "合并：多个一致精确值")

# 多个矛盾精确值 → 逐行错误
errs = agg_err("1.5 m\n2.0 m")
check(len(errs) == 2 and [e["line"] for e in errs] == [1, 2]
      and "精确值" in errs[0]["message"], "合并：矛盾精确值逐行报错")

# 未知单位标明行号
errs = agg_err("1.0±0.1 m\n2.0±0.1 blorp")
check(errs[0]["line"] == 2 and "未知单位" in errs[0]["message"],
      "合并：未知单位标明行号")

# 量纲不符标明行号
errs = agg_err("1.0±0.1 m\n2.0±0.1 s")
check(errs[0]["line"] == 2 and "量纲不符" in errs[0]["message"],
      "合并：量纲不符标明行号")

# 格式错误标明行号
errs = agg_err("1.0±0.1 m\n2.0± m")
check(errs[0]["line"] == 2 and errs[0]["position"] is not None,
      "合并：格式错误标明行号")

# 输出单位量纲不符
errs = agg_err("1.0±0.1 m", "s")
check(errs[0]["field"] == "unit" and "量纲" in errs[0]["message"],
      "合并：输出单位量纲校验")

# 空输入
errs = agg_err("  \n  ")
check("至少" in errs[0]["message"], "合并：空输入报错")

print(f"\n全部 {PASSED} 项检查通过。")
