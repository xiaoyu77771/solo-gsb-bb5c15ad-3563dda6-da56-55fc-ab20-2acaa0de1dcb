"""API 冒烟测试：使用临时数据库。"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DB_PATH"] = os.path.join(tmp, "test.db")
        # 环境变量需在导入前生效，故此处重新加载模块
        import importlib

        import app.database as database
        import app.main as main

        importlib.reload(database)
        importlib.reload(main)
        with TestClient(main.app) as c:
            yield c


def test_register_and_canonical_conflict(client):
    r = client.post("/namespaces/game/names", json={"name": "Admin"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Admin"
    assert body["canonical_name"] == "admin"

    # NFKC + casefold 后规范名相同 -> 409
    r = client.post("/namespaces/game/names", json={"name": "ＡＤＭＩＮ"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["canonical_name"] == "admin"
    assert detail["conflicts"][0]["reason"] == "canonical_match"


def test_confusable_conflict(client):
    assert client.post("/namespaces/game/names", json={"name": "alice"}).status_code == 201
    # 数字 1（Common 脚本，不触发 422）仿冒字母 l，规范名不同但可混淆
    r = client.post("/namespaces/game/names", json={"name": "a1ice"})
    assert r.status_code == 409
    assert r.json()["detail"]["conflicts"][0]["reason"] == "confusable"


def test_mixed_script_422(client):
    # Latin + Cyrillic
    r = client.post("/namespaces/game/names", json={"name": "Admіn"})
    assert r.status_code == 422
    scripts = r.json()["detail"]["scripts"]
    assert set(scripts) == {"Latin", "Cyrillic"}
    assert any(c["codepoint"] == "U+0456" for c in scripts["Cyrillic"])

    # Latin + Greek，且含 Common 字符（数字应被忽略，不影响判定）
    r = client.post("/namespaces/game/names", json={"name": "alphα1"})
    assert r.status_code == 422
    assert set(r.json()["detail"]["scripts"]) == {"Latin", "Greek"}


def test_namespaces_are_isolated(client):
    assert client.post("/namespaces/a/names", json={"name": "bob"}).status_code == 201
    assert client.post("/namespaces/b/names", json={"name": "bob"}).status_code == 201


def test_check_endpoint_does_not_persist(client):
    r = client.post("/namespaces/game/names/check", json={"name": "Carol"})
    assert r.status_code == 200
    body = r.json()
    assert body["canonical_name"] == "carol"
    assert body["registrable"] is True
    assert body["mixed_script"] is False
    assert client.get("/namespaces/game/names").json() == []

    # 注册后 check 能发现冲突，但仍不落库
    assert client.post("/namespaces/game/names", json={"name": "Carol"}).status_code == 201
    r = client.post("/namespaces/game/names/check", json={"name": "Сarol"})  # Cyrillic С
    assert r.status_code == 200
    body = r.json()
    assert body["registrable"] is False
    assert body["conflicts"][0]["reason"] == "confusable"
    assert len(client.get("/namespaces/game/names").json()) == 1
