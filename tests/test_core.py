"""核心功能自测：解析、换算、误差传播与三类错误。直接运行：python tests/test_core.py"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.evaluator import EvalError, evaluate  # noqa: E402

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

print(f"\n全部 {PASSED} 项检查通过。")
