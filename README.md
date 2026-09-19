# Unicode 显示名防仿冒 API

命名空间（namespace）内的显示名注册服务，基于 **FastAPI + SQLite + confusables + unicodedataplus**，在注册时拦截三类仿冒：

| 判定 | 规则 | 结果 |
| --- | --- | --- |
| 规范名查重 | NFKC + casefold 后与同命名空间已有规范名比较 | 相同 → `409` |
| 同形字符 | 与已有名称**逐条**做 Unicode confusables 判定 | 可混淆 → `409` |
| 混脚本 | 忽略 Common / Inherited 后，同时含 Latin、Cyrillic、Greek 中两种及以上脚本 | `422`，并列出脚本及对应码点 |

原名始终原样落库，规范名（`normalized_name`）一并保存；`(namespace, normalized_name)` 在数据库层有唯一约束兜底并发写入。

## 快速开始（Docker，单条命令）

```bash
docker compose up --build
```

该命令完成镜像构建、依赖安装与数据库初始化（应用启动时自动建库建表，SQLite 文件落在命名卷 `names-data` 中）。

- **API 地址：http://localhost:8000**
- **交互式文档（Swagger UI）：http://localhost:8000/docs**
- **端口：8000**（可在 `docker-compose.yml` 的 `ports` 中调整）

## 本地开发（单条命令）

```bash
./scripts/setup.sh    # 安装依赖 + 初始化数据库（./names.db）
uvicorn app.main:app --reload --port 8000
```

`setup.sh` 内部执行 `pip install -r requirements.txt` 与 `python -m app.database`；如需虚拟环境，先自行激活再运行该脚本即可。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/namespaces/{namespace}/names` | 注册显示名：`201` 成功；`409` 规范名相同或同形冲突；`422` 混脚本违规 |
| `POST` | `/namespaces/{namespace}/check` | **只分析不落库**：返回规范名、脚本分析、码点与潜在冲突 |
| `GET` | `/namespaces/{namespace}/names` | 列出命名空间内已注册名称 |
| `GET` | `/health` | 健康检查 |

请求体均为 `{"name": "<显示名>"}`（1–64 字符，非空白）。

### 示例

注册成功：

```bash
curl -X POST http://localhost:8000/namespaces/chat/names \
  -H 'Content-Type: application/json' -d '{"name": "paypal"}'
# 201 {"id":1,"namespace":"chat","original_name":"paypal","normalized_name":"paypal",...}
```

规范名相同（大小写 / 全半角等兼容字符折叠后重复）→ `409`：

```bash
curl -X POST http://localhost:8000/namespaces/chat/names \
  -H 'Content-Type: application/json' -d '{"name": "PAYPAL"}'
# 409 {"detail":{"error":"name_conflict","normalized_name":"paypal",
#      "conflicts":[{"id":1,"original_name":"paypal","reason":"normalized_match",...}]}}
```

同形字符（纯西里尔 `арр` 仿冒拉丁 `app`）→ `409`：

```bash
curl -X POST http://localhost:8000/namespaces/chat/names \
  -H 'Content-Type: application/json' -d '{"name": "арр"}'
# 409 {"detail":{"error":"name_conflict",
#      "conflicts":[{"original_name":"app","reason":"confusable",...}]}}
```

混脚本（拉丁 `ad` + 西里尔 `м` + 拉丁 `in`）→ `422`，列出脚本及码点：

```bash
curl -X POST http://localhost:8000/namespaces/chat/names \
  -H 'Content-Type: application/json' -d '{"name": "adмin"}'
# 422 {"detail":{"error":"mixed_script_violation",
#      "restricted_scripts_used":["Cyrillic","Latin"],
#      "script_details":[{"script":"Cyrillic","characters":["м"],"code_points":["U+043C"]},
#                        {"script":"Latin","characters":["a","d","i","n"],
#                         "code_points":["U+0061","U+0064","U+0069","U+006E"]}]}}
```

只分析不落库：

```bash
curl -X POST http://localhost:8000/namespaces/chat/check \
  -H 'Content-Type: application/json' -d '{"name": "арр"}'
# 200 {"normalized_name":"арр","mixed_script_violation":false,
#      "scripts":["Cyrillic"],"conflicts":[{"reason":"confusable",...}], ...}
```

## 判定规则说明

1. **规范化**：`unicodedataplus.normalize("NFKC", name).casefold()`。NFKC 折叠全半角、合字等兼容字符，casefold 折叠大小写（比 lower 更彻底，如 `ß`→`ss`）。
2. **冲突检测**：候选规范名与同命名空间内每条已有规范名比较——完全相等记为 `normalized_match`；否则用 `confusables.is_confusable` 做基于 Unicode `confusables.txt` 的同形判定，命中记为 `confusable`。命名空间之间相互隔离。
3. **混脚本检测**：逐字符取 `unicodedataplus.script()`，忽略 `Common`（数字、标点、空白等）与 `Inherited`（组合符）后，若出现的脚本中包含 Latin / Cyrillic / Greek 中的两种及以上，判定违规。纯西里尔、纯希腊或与 Han 等其他脚本混用不触发本规则（仍受同形判定约束）。

## 运行测试

```bash
pip install -r requirements-dev.txt
pytest
```

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_PATH` | `./names.db`（容器内 `/data/names.db`） | SQLite 数据库文件路径 |

## 项目结构

```
app/
  main.py       # FastAPI 路由与错误响应（201/409/422）
  service.py    # 注册/分析业务逻辑，逐条冲突判定
  analysis.py   # NFKC+casefold 规范化、脚本与码点分析
  database.py   # SQLite 连接与建表（python -m app.database 可独立初始化）
  schemas.py    # Pydantic 请求/响应模型
tests/test_api.py
Dockerfile  docker-compose.yml  scripts/setup.sh
requirements.txt  requirements-dev.txt
```
