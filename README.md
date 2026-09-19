# Unicode 显示名防仿冒 API

基于 **FastAPI + SQLite + confusables + unicodedataplus** 的命名空间内显示名防仿冒服务。

## 功能

- **注册显示名**：保存原名，并计算 **NFKC + casefold** 规范名；与同命名空间已有名称**逐条做 Unicode 同形字符（confusable）判定**。规范名相同或可混淆时返回 **409** 及冲突记录。
- **混脚本限制**：忽略 `Common`、`Inherited` 脚本后，名称同时含 **Latin / Cyrillic / Greek 中两种及以上**脚本时返回 **422**，并列出脚本及对应码点。
- **检查接口**：只分析不落库，返回规范名、脚本统计、混脚本判定与潜在冲突。
- 命名空间之间相互隔离；`(namespace, canonical_name)` 唯一约束兜底并发写入。

## 快速开始（单条命令）

### Docker Compose（推荐）

```bash
docker compose up --build
```

该命令自动完成依赖安装与数据库初始化。

- **API 地址**：`http://localhost:8000`
- **交互式文档**：`http://localhost:8000/docs`
- 数据持久化在命名卷 `names-data`（容器内 `/data/names.db`）。

### 本地运行

```bash
pip install -r requirements.txt && python -m app.database && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- 数据库默认文件为 `./names.db`，可用环境变量 `APP_DB_PATH` 覆盖。
- 应用启动时也会自动执行幂等建表，`python -m app.database` 用于显式初始化。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/namespaces/{namespace}/names` | 注册显示名：`201` 成功；`409` 规范名相同/可混淆（附冲突记录）；`422` 混脚本（附脚本与码点） |
| `POST` | `/namespaces/{namespace}/names/check` | 只分析不落库：返回规范名、脚本、混脚本标记、冲突与 `registrable` |
| `GET` | `/namespaces/{namespace}/names` | 列出命名空间内已注册名称 |
| `GET` | `/health` | 健康检查 |

### 示例

```bash
# 注册
curl -X POST localhost:8000/namespaces/game/names \
  -H 'Content-Type: application/json' -d '{"name":"Admin"}'
# 201 {"id":1,"namespace":"game","name":"Admin","canonical_name":"admin",...}

# 全角字符 NFKC 归一后规范名相同 -> 409
curl -X POST localhost:8000/namespaces/game/names \
  -H 'Content-Type: application/json' -d '{"name":"ＡＤＭＩＮ"}'
# 409 {"detail":{"message":"...","canonical_name":"admin",
#      "conflicts":[{"id":1,"name":"Admin","canonical_name":"admin","reason":"canonical_match"}]}}

# 混入西里尔字符 -> 422
curl -X POST localhost:8000/namespaces/game/names \
  -H 'Content-Type: application/json' -d '{"name":"Admіn"}'
# 422 {"detail":{"message":"...","scripts":{
#      "Cyrillic":[{"character":"і","codepoint":"U+0456"}],
#      "Latin":[{"character":"A","codepoint":"U+0041"},...]}}}

# 只检查不落库
curl -X POST localhost:8000/namespaces/game/names/check \
  -H 'Content-Type: application/json' -d '{"name":"alice"}'
# 200 {"canonical_name":"alice","scripts":{...},"mixed_script":false,
#      "conflicts":[],"registrable":true}
```

## 判定规则

1. **规范名**：`unicodedataplus.normalize("NFKC", name).casefold()`。
2. **冲突**：与同命名空间每条已注册名称比较——规范名相同记 `canonical_match`；否则用 `confusables.is_confusable` 对原名逐字符（含多字符贪婪匹配）判定，可混淆记 `confusable`。
3. **混脚本**：逐字符取 `unicodedataplus.script()`，忽略 `Common`/`Inherited`；命中 Latin、Cyrillic、Greek 中两种及以上即拒绝。

## 测试

```bash
pip install pytest httpx && python -m pytest tests/
```

## 项目结构

```
app/
  main.py       # FastAPI 路由与注册/检查流程
  analysis.py   # 规范化、脚本统计、confusable 判定
  database.py   # SQLite 建表与连接（python -m app.database 可初始化）
  schemas.py    # Pydantic 模型
tests/test_api.py
Dockerfile / docker-compose.yml / requirements.txt
```
