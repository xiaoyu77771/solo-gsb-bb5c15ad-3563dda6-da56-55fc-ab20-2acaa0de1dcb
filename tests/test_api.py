"""端到端 API 测试：每个用例使用独立的临时 SQLite 数据库。"""
import pytest
from fastapi.testclient import TestClient

from app import database
from app.main import app

# 纯西里尔字母 "арр"（а U+0430, р U+0440），与拉丁 "app" 同形
CYRILLIC_APP = "арр"
# 拉丁 "ad" + 西里尔 "м"（U+043C）+ 拉丁 "in" —— 混脚本
MIXED_ADMIN = "adмin"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))
    database.init_db(str(db_path))
    with TestClient(app) as test_client:
        yield test_client


def register(client, name, namespace="chat"):
    return client.post(f"/namespaces/{namespace}/names", json={"name": name})


def test_register_returns_201_and_stores_original_and_normalized(client):
    resp = register(client, "Ａｌｉｃｅ")  # 全角字母
    assert resp.status_code == 201
    body = resp.json()
    assert body["original_name"] == "Ａｌｉｃｅ"  # 原名落库
    assert body["normalized_name"] == "alice"  # NFKC + casefold
    assert body["namespace"] == "chat"
    assert body["id"] >= 1


def test_normalized_duplicate_returns_409_with_conflict_record(client):
    assert register(client, "Alice").status_code == 201

    resp = register(client, "ALICE")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "name_conflict"
    assert detail["normalized_name"] == "alice"
    assert detail["conflicts"][0]["original_name"] == "Alice"
    assert detail["conflicts"][0]["reason"] == "normalized_match"

    # NFKC 兼容字符（全角）折叠后同样冲突
    resp = register(client, "Ａｌｉｃｅ")
    assert resp.status_code == 409
    assert resp.json()["detail"]["conflicts"][0]["reason"] == "normalized_match"


def test_confusable_name_returns_409(client):
    assert register(client, "app").status_code == 201

    resp = register(client, CYRILLIC_APP)  # 纯西里尔，单脚本不触发 422
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["conflicts"][0]["reason"] == "confusable"
    assert detail["conflicts"][0]["original_name"] == "app"

    # 反向同样成立：先注册纯西里尔，再注册拉丁
    assert register(client, CYRILLIC_APP, namespace="other").status_code == 201
    resp = register(client, "app", namespace="other")
    assert resp.status_code == 409
    assert resp.json()["detail"]["conflicts"][0]["reason"] == "confusable"


def test_mixed_latin_cyrillic_returns_422_with_code_points(client):
    resp = register(client, MIXED_ADMIN)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "mixed_script_violation"
    assert detail["restricted_scripts_used"] == ["Cyrillic", "Latin"]

    by_script = {d["script"]: d for d in detail["script_details"]}
    assert by_script["Cyrillic"]["characters"] == ["м"]
    assert by_script["Cyrillic"]["code_points"] == ["U+043C"]
    assert set(by_script["Latin"]["characters"]) == {"a", "d", "i", "n"}
    assert "U+0061" in by_script["Latin"]["code_points"]

    # 422 不落库
    assert client.get("/namespaces/chat/names").json() == []


def test_mixed_latin_greek_returns_422(client):
    resp = register(client, "Αlpha")  # 希腊大写 Alpha + 拉丁
    assert resp.status_code == 422
    assert resp.json()["detail"]["restricted_scripts_used"] == ["Greek", "Latin"]


def test_single_restricted_script_is_allowed(client):
    assert register(client, "αρρ").status_code == 201  # 纯西里尔
    assert register(client, "ΑΒΓ").status_code == 201  # 纯希腊
    assert register(client, "hello-123_世界").status_code == 201  # Latin+Han 不拦截


def test_check_endpoint_analyzes_without_persisting(client):
    assert register(client, "app").status_code == 201

    resp = client.post("/namespaces/chat/check", json={"name": CYRILLIC_APP})
    assert resp.status_code == 200
    body = resp.json()
    assert body["normalized_name"] == CYRILLIC_APP
    assert body["mixed_script_violation"] is False
    assert body["scripts"] == ["Cyrillic"]
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["reason"] == "confusable"

    # 检查接口不落库：命名空间内仍只有 1 条记录
    names = client.get("/namespaces/chat/names").json()
    assert [n["original_name"] for n in names] == ["app"]


def test_check_endpoint_reports_mixed_scripts_without_persisting(client):
    resp = client.post("/namespaces/chat/check", json={"name": MIXED_ADMIN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mixed_script_violation"] is True
    assert body["restricted_scripts_used"] == ["Cyrillic", "Latin"]
    assert client.get("/namespaces/chat/names").json() == []


def test_namespaces_are_isolated(client):
    assert register(client, "root", namespace="a").status_code == 201
    assert register(client, "root", namespace="b").status_code == 201
    assert len(client.get("/namespaces/a/names").json()) == 1
    assert len(client.get("/namespaces/b/names").json()) == 1


def test_blank_name_rejected(client):
    assert register(client, "   ").status_code == 422
    assert register(client, "").status_code == 422


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
