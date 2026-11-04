"""流代理服务测试：仅在本地装了 server 依赖时运行。

APK 构建不需要 server 依赖，因此 CI 里会自动跳过。
"""
import importlib

import pytest

pytest.importorskip("flask")
pytest.importorskip("Crypto")


def test_stream_health():
    mod = importlib.import_module("server.stream_server")
    client = mod.app.test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
