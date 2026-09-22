# 实验测量单位校验 Web 应用

输入带单位的测量值与表达式，系统自动解析括号、乘除、幂与 SI 词头，按维度（量纲）执行单位换算，并用**一阶误差传播**计算结果的不确定度。对量纲不兼容、零除和非法指数给出**字段级错误**（含出错位置）。支持保存计算条目、复制输入、导出 JSON/CSV。

- 后端：FastAPI + SQLite
- 前端：原生 JavaScript（无构建步骤）
- 部署：Docker Compose 一键启动

## 快速开始（Docker）

```bash
docker compose up --build
```

启动后访问：

| 地址 | 说明 |
| --- | --- |
| **http://localhost:8000** | Web 应用主界面 |
| http://localhost:8000/docs | 交互式 API 文档（Swagger UI） |

数据通过命名卷 `app-data` 持久化（容器内 `/data/app.db`）。停止：`docker compose down`。

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# 访问 http://localhost:8000
```

运行核心逻辑自测（23 项）：

```bash
python tests/test_core.py
```

## 表达式语法

```
值       := 数字 [± 不确定度[%]] [单位] | ( 表达式 ) [单位] | 单位
表达式   := 值 的 + - * / ^ （^ 或 ** 表示幂，· 或空格表示单位相乘）
换算     := 表达式 to 目标单位        （也可用 ->）
```

示例：

| 输入 | 输出 |
| --- | --- |
| `2.5±0.1 km/h * 3.0±0.1 h to km` | `7.50 ± 0.39 km` |
| `9.8±0.05 m/s^2 * 65±0.5 kg` | `637.0 ± 5.9 N`（自动识别导出单位） |
| `100±2 kPa * 2.5±0.05 L to J` | `250.0 ± 7.1 J` |
| `1.5±0.02 V / 0.75±0.01 mA to Ω` | `2000 ± 38 Ω` |
| `(4.0±0.1 m)^2 to m^2` | `16.00 ± 0.80 m²` |
| `1 kWh to J` | `3600000 J` |
| `2.5±2% V` | `2.500 ± 0.050 V`（不确定度按百分比解析） |

语法要点：

- **不确定度**：`值±不确定度`，或 `值±百分比%`；不带 `±` 的数视为精确值。
- **单位**：SI 基本/导出单位（`m kg s A K mol cd`、`N Pa J W V Ω …`）、常用单位（`min h L bar atm eV cal Wh …`）及全部 **SI 词头**（`k M G m µ n p …`，如 `km`、`mJ`、`µm`、`kWh`）。
- **单位表达式**：`kg·m/s^2`、`km/h`、`m/s^2`、`m²`、`m⁻²`、`1/mol` 均可；空格等价于 `·`。
- **幂**：`^` 或 `**`，右结合；上标 `² ³ ⁻¹` 直接识别。
- **换算**：末尾加 `to 目标单位`，系统校验量纲后换算；不加 `to` 时结果以 SI 单位表示。

## 误差传播规则（一阶、假设各量独立）

| 运算 | 不确定度 |
| --- | --- |
| 加减 `a ± b` | `σ = √(σa² + σb²)` |
| 乘法 `a·b` | `σ = √((b·σa)² + (a·σb)²)` |
| 除法 `a/b` | `σ = √((σa/b)² + (a·σb/b²)²)` |
| 幂 `xⁿ` | `σ = \|n·xⁿ⁻¹\|·σx`（`n` 带不确定度时附加 `\|xⁿ·ln x\|·σn` 项） |

结果显示时，不确定度保留两位有效数字，测量值对齐到同一小数位。

## 字段级错误

所有错误以 `{"ok": false, "errors": [{"field", "message", "position"}]}` 返回，前端在对应字段下标注出错位置：

| 类型 | 示例 | 报错 |
| --- | --- | --- |
| 量纲不兼容 | `1 m + 1 s` | `量纲不兼容：L 与 T 不能相加减` |
| 零除 | `5 / (3-3)` | `除数为零` |
| 非法指数 | `(2 m)^(1 s)` | `非法指数：指数必须是无量纲数…` |
| 非法指数 | `(-2)^0.5`、`0^0` | `负数不能取非整数次幂` / `0 不能取非正数次幂` |
| 换算量纲不符 | `1 m to s` | `量纲不匹配：结果量纲为 L…` |
| 未知单位 | `2 blorp` | `未知单位 'blorp'…` |
| 表单校验 | 空表达式、名称超长 | `field: expression / name` |

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/evaluate` | 求值（不保存）。Body: `{"expression": "..."}` |
| POST | `/api/calculations` | 求值并保存条目。Body: `{"name": "...", "expression": "..."}` |
| GET | `/api/calculations` | 列出已保存条目 |
| DELETE | `/api/calculations/{id}` | 删除条目 |
| GET | `/api/export.json` | 导出全部条目（JSON 附件） |
| GET | `/api/export.csv` | 导出全部条目（CSV 附件，带 BOM） |

## 项目结构

```
├── docker-compose.yml   # 一键启动
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py          # FastAPI 路由（API + 静态页面）
│   ├── evaluator.py     # 词法/语法分析、量纲运算、一阶误差传播
│   ├── units.py         # SI 单位、词头、量纲向量与显示
│   ├── database.py      # SQLite 持久化
│   └── static/          # 原生前端（index.html / app.js / style.css）
└── tests/test_core.py   # 核心逻辑自测
```

环境变量 `DB_PATH` 可指定 SQLite 文件位置（容器内默认 `/data/app.db`，本地默认 `./data/app.db`）。
