"use strict";

const $ = (id) => document.getElementById(id);

const FIELD_NAMES = { expression: "表达式", name: "名称" };

const SYMBOLS = ["±", "·", "²", "³", "⁻", "µ", "Ω", "^", "%"];

const EXAMPLES = [
  "2.5±0.1 km/h * 3.0±0.1 h to km",
  "9.8±0.05 m/s^2 * 65±0.5 kg to N",
  "100±2 kPa * 2.5±0.05 L to J",
  "1.5±0.02 V / 0.75±0.01 mA to Ω",
  "500±5 mg + 1.2±0.01 g to g",
  "(4.0±0.1 m)^2 to m^2",
  "1 kWh to J",
  "2 µm to nm",
];

// ------------------------------------------------------------ 工具

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

let toastTimer = null;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 1800);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  toast("已复制到剪贴板");
}

function insertAtCursor(input, text) {
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? input.value.length;
  input.value = input.value.slice(0, start) + text + input.value.slice(end);
  input.focus();
  input.selectionStart = input.selectionEnd = start + text.length;
}

async function api(path, options) {
  const res = await fetch(path, options);
  return res.json();
}

// ------------------------------------------------------------ 计算与展示

function showErrors(errors) {
  const box = $("error-box");
  $("result-box").classList.add("hidden");
  box.classList.remove("hidden");
  box.innerHTML = "";
  const expr = $("expr").value;
  for (const e of errors) {
    const div = document.createElement("div");
    div.className = "error-item";
    const field = FIELD_NAMES[e.field] || e.field;
    let html = `<strong>${escapeHtml(field)}</strong>：${escapeHtml(e.message)}`;
    if (e.field === "expression" && e.position != null && e.position >= 0) {
      const pos = Math.min(e.position, expr.length);
      html += `<pre>${escapeHtml(expr)}\n${" ".repeat(pos)}^</pre>`;
    }
    div.innerHTML = html;
    box.appendChild(div);
  }
}

function showResult(r) {
  $("error-box").classList.add("hidden");
  const box = $("result-box");
  box.classList.remove("hidden");
  const rows = [];
  if (r.si && r.si.formatted !== r.formatted) {
    rows.push(`<div><span>SI 换算</span><b>${escapeHtml(r.si.formatted)}</b></div>`);
  }
  rows.push(`<div><span>量纲</span><b>${escapeHtml(r.dimension)}</b></div>`);
  if (r.relative_uncertainty != null && r.relative_uncertainty !== "") {
    const rel = (r.relative_uncertainty * 100).toPrecision(3);
    rows.push(`<div><span>相对不确定度</span><b>${rel} %</b></div>`);
  }
  box.innerHTML = `
    <div class="result-main">${escapeHtml(r.formatted)}</div>
    <div class="result-rows">${rows.join("")}</div>
    <button id="btn-copy-result" class="mini">复制结果</button>`;
  $("btn-copy-result").onclick = () => copyText(r.formatted);
}

async function doEvaluate() {
  const expression = $("expr").value;
  const data = await api("/api/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expression }),
  });
  if (data.ok) showResult(data.result);
  else showErrors(data.errors);
  return data.ok;
}

async function doSave() {
  const payload = { expression: $("expr").value, name: $("name").value };
  const data = await api("/api/calculations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!data.ok) {
    showErrors(data.errors);
    return;
  }
  if (data.entry.status === "ok") {
    toast("已保存");
  } else {
    toast("已保存（求值失败：" + data.entry.error + "）");
  }
  loadHistory();
}

// ------------------------------------------------------------ 重复测量合并

const AGG_EXAMPLE = "2.5±0.1 km\n2.62±0.08 km\n2.55±0.05 km";

function showAggErrors(errors) {
  const box = $("agg-error-box");
  $("agg-result-box").classList.add("hidden");
  box.classList.remove("hidden");
  box.innerHTML = "";
  const lines = $("agg-lines").value.split("\n");
  for (const e of errors) {
    const div = document.createElement("div");
    div.className = "error-item";
    const where = e.line != null ? `第 ${e.line} 行`
      : (e.field === "unit" ? "输出单位" : "输入");
    let html = `<strong>${where}</strong>：${escapeHtml(e.message)}`;
    if (e.line != null && e.position != null && e.position >= 0) {
      const text = (lines[e.line - 1] || "").trim();
      const pos = Math.min(e.position, text.length);
      html += `<pre>${escapeHtml(text)}\n${" ".repeat(pos)}^</pre>`;
    }
    div.innerHTML = html;
    box.appendChild(div);
  }
}

function showAggResult(r, rows) {
  $("agg-error-box").classList.add("hidden");
  const box = $("agg-result-box");
  box.classList.remove("hidden");
  const info = [];
  info.push(`<div><span>合并方式</span><b>${r.method === "exact" ? "精确值（无不确定度）" : "逆方差加权平均"}</b></div>`);
  info.push(`<div><span>有效行数</span><b>${r.count}</b></div>`);
  if (r.si && r.si.formatted !== r.formatted) {
    info.push(`<div><span>SI 换算</span><b>${escapeHtml(r.si.formatted)}</b></div>`);
  }
  info.push(`<div><span>量纲</span><b>${escapeHtml(r.dimension)}</b></div>`);
  if (typeof r.relative_uncertainty === "number") {
    const rel = (r.relative_uncertainty * 100).toPrecision(3);
    info.push(`<div><span>相对不确定度</span><b>${rel} %</b></div>`);
  }
  const body = rows.map((row) => `
    <tr>
      <td>${row.line}</td>
      <td><code>${escapeHtml(row.input)}</code></td>
      <td class="ok-value">${escapeHtml(row.formatted)}</td>
      <td>${row.exact ? "∞（精确）" : (row.weight == null ? "—" : Number(row.weight).toPrecision(3))}</td>
    </tr>`).join("");
  box.innerHTML = `
    <div class="result-main">${escapeHtml(r.formatted)}</div>
    <div class="result-rows">${info.join("")}</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>行</th><th>输入</th><th>数值</th><th>权重</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
    <button id="btn-copy-agg" class="mini">复制结果</button>`;
  $("btn-copy-agg").onclick = () => copyText(r.formatted);
}

async function doAggregate() {
  const data = await api("/api/aggregate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lines: $("agg-lines").value,
      unit: $("agg-unit").value,
    }),
  });
  if (data.ok) showAggResult(data.result, data.rows);
  else showAggErrors(data.errors);
}

// ------------------------------------------------------------ 历史记录

function renderHistory(items) {
  const tbody = $("history").querySelector("tbody");
  tbody.innerHTML = "";
  $("history-empty").classList.toggle("hidden", items.length > 0);
  for (const it of items) {
    const tr = document.createElement("tr");
    const resultHtml = it.status === "ok"
      ? `<span class="ok-value">${escapeHtml(it.formatted ?? "")}</span>`
      : `<span class="err-value" title="${escapeHtml(it.error ?? "")}">错误：${escapeHtml(it.error ?? "")}</span>`;
    tr.innerHTML = `
      <td>${escapeHtml(it.name || "—")}</td>
      <td><code>${escapeHtml(it.expression)}</code></td>
      <td>${resultHtml}</td>
      <td class="nowrap">${escapeHtml((it.created_at || "").replace("T", " ").replace("+00:00", "Z"))}</td>
      <td class="nowrap row-actions"></td>`;
    const actions = tr.querySelector(".row-actions");
    const mkBtn = (label, fn) => {
      const b = document.createElement("button");
      b.className = "mini";
      b.textContent = label;
      b.onclick = fn;
      actions.appendChild(b);
    };
    mkBtn("载入", () => {
      $("expr").value = it.expression;
      $("name").value = it.name || "";
      $("expr").focus();
    });
    mkBtn("复制", () => copyText(it.expression));
    mkBtn("删除", async () => {
      await api(`/api/calculations/${it.id}`, { method: "DELETE" });
      loadHistory();
    });
    tbody.appendChild(tr);
  }
}

async function loadHistory() {
  const data = await api("/api/calculations");
  renderHistory(data.items || []);
}

// ------------------------------------------------------------ 初始化

function init() {
  for (const s of SYMBOLS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = s;
    b.onclick = () => insertAtCursor($("expr"), s);
    $("symbol-chips").appendChild(b);
  }
  for (const ex of EXAMPLES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip example";
    b.textContent = ex;
    b.onclick = () => { $("expr").value = ex; $("expr").focus(); };
    $("examples").appendChild(b);
  }

  $("btn-eval").onclick = doEvaluate;
  $("btn-save").onclick = doSave;
  $("btn-copy").onclick = () => copyText($("expr").value);
  $("btn-clear").onclick = () => {
    $("expr").value = "";
    $("error-box").classList.add("hidden");
    $("result-box").classList.add("hidden");
    $("expr").focus();
  };
  $("btn-export-json").onclick = () => { window.location = "/api/export.json"; };
  $("btn-export-csv").onclick = () => { window.location = "/api/export.csv"; };
  $("btn-refresh").onclick = loadHistory;
  $("expr").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doEvaluate();
  });

  $("btn-agg").onclick = doAggregate;
  $("btn-agg-example").onclick = () => {
    $("agg-lines").value = AGG_EXAMPLE;
    $("agg-unit").value = "km";
    $("agg-lines").focus();
  };
  $("btn-agg-clear").onclick = () => {
    $("agg-lines").value = "";
    $("agg-unit").value = "";
    $("agg-error-box").classList.add("hidden");
    $("agg-result-box").classList.add("hidden");
    $("agg-lines").focus();
  };
  $("agg-lines").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) doAggregate();
  });

  loadHistory();
}

init();
