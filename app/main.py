"""FastAPI 应用：实验测量单位校验服务。"""
from __future__ import annotations

import csv
import io
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import database
from .evaluator import EvalError, evaluate


@asynccontextmanager
async def lifespan(_app):
    database.init_db()
    yield


app = FastAPI(title="实验测量单位校验", version="1.0.0", lifespan=lifespan,
              description="解析带单位的测量表达式，执行量纲换算与一阶误差传播。")


class EvaluateIn(BaseModel):
    expression: str = ""


class SaveIn(BaseModel):
    name: str = ""
    expression: str = ""


def _err(field: str, message: str, pos: int | None = None) -> dict:
    return {"field": field, "message": message, "position": pos}


@app.post("/api/evaluate")
def api_evaluate(body: EvaluateIn):
    """求值表达式，不保存。错误以字段级形式返回。"""
    expr = body.expression.strip()
    if not expr:
        return {"ok": False,
                "errors": [_err("expression", "表达式不能为空", 0)]}
    try:
        result = evaluate(expr)
    except EvalError as e:
        return {"ok": False, "errors": [_err(e.field, e.message, e.pos)]}
    return {"ok": True, "result": result}


@app.post("/api/calculations", status_code=201)
def api_save(body: SaveIn):
    """求值并保存计算条目（求值失败的表达式也会以 error 状态存档）。"""
    errors = []
    expr = body.expression.strip()
    name = body.name.strip()
    if not expr:
        errors.append(_err("expression", "表达式不能为空", 0))
    if len(name) > 80:
        errors.append(_err("name", "名称不能超过 80 个字符"))
    if errors:
        return JSONResponse(status_code=400,
                            content={"ok": False, "errors": errors})
    try:
        result, status, errmsg = evaluate(expr), "ok", None
    except EvalError as e:
        result, status, errmsg = None, "error", e.message
    entry = database.insert_calc(name, expr, result, status, errmsg)
    return {"ok": True, "entry": entry}


@app.get("/api/calculations")
def api_list():
    return {"items": database.list_calcs()}


@app.delete("/api/calculations/{cid}")
def api_delete(cid: int):
    if not database.delete_calc(cid):
        raise HTTPException(status_code=404, detail="条目不存在")
    return {"ok": True}


_CSV_FIELDS = ["id", "name", "expression", "status", "value", "uncertainty",
               "unit", "si_value", "si_uncertainty", "si_unit", "formatted",
               "dimension", "error", "created_at"]


@app.get("/api/export.json")
def api_export_json():
    items = database.list_calcs()
    return JSONResponse(
        content=items,
        headers={"Content-Disposition":
                 "attachment; filename=calculations.json"})


@app.get("/api/export.csv")
def api_export_csv():
    items = database.list_calcs()
    buf = io.StringIO()
    buf.write("﻿")  # BOM，便于 Excel 识别 UTF-8
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for item in items:
        writer.writerow({k: item.get(k) for k in _CSV_FIELDS})
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 "attachment; filename=calculations.csv"})


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
