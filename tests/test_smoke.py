"""框架冒烟测试：导入、平台开关、播放来源与视图构建。"""
import os

os.environ.setdefault("STREAM_BASE", "")


def _handlers():
    return {
        "rerender": lambda: None,
        "on_search": lambda: None,
        "on_open_detail": lambda sid: None,
        "on_back": lambda e=None: None,
        "on_play": lambda ep, vid: None,
    }


def test_imports():
    import flet  # noqa: F401
    import flet_video  # noqa: F401
    from app.platform import is_mobile, is_android  # noqa: F401
    from app.config import ENABLE_DOWNLOAD, ENABLE_CACHE_MANAGER  # noqa: F401
    from app.storage import data_dir  # noqa: F401
    from app.services.playback_service import resolve_play_url
    assert resolve_play_url("v1") is not None


def test_mock_search():
    from app.services.mock_service import search, get_drama
    res = search("框架")
    assert len(res) >= 1
    drama = get_drama(res[0]["series_id"])
    assert drama is not None
    assert drama["vid_list"]


def test_settings_roundtrip(tmp_path, monkeypatch):
    from app import settings
    from app.services.playback_service import resolve_play_url

    monkeypatch.setattr(settings, "data_dir", lambda: str(tmp_path))
    monkeypatch.delenv("STREAM_BASE", raising=False)

    settings.set_stream_base("https://demo.tunnel.test/stream/")
    assert settings.stream_base() == "https://demo.tunnel.test/stream"
    assert resolve_play_url("7666404568275635224") == "https://demo.tunnel.test/stream/7666404568275635224.mp4"


def test_views_build():
    from app.core.state import AppState
    from app.ui.views import build_app_view
    from app.services.mock_service import search, get_drama

    handlers = _handlers()
    state = AppState()
    assert build_app_view(state, handlers) is not None

    state.keyword = "框架"
    state.search_results = search(state.keyword)
    assert build_app_view(state, handlers) is not None

    # 带封面的真实结构，确保图片控件构建路径被覆盖
    state.search_results = [
        {
            "series_id": "1",
            "series_name": "带封面",
            "episode_cnt": 2,
            "series_cover": "https://example.com/cover.jpg",
            "tags": ["都市", "逆袭"],
            "vid_list": ["v1", "v2"],
        }
    ]
    assert build_app_view(state, handlers) is not None

    state.current_drama = get_drama("1001")
    state.current_view = "detail"
    assert build_app_view(state, handlers) is not None

    state.current_drama = {
        "series_id": "1",
        "series_name": "带封面详情",
        "episode_cnt": 2,
        "series_cover": "https://example.com/cover.jpg",
        "series_intro": "简介内容",
        "tags": ["都市"],
        "vid_list": ["v1", "v2"],
    }
    assert build_app_view(state, handlers) is not None

    state.play_title = "第1集"
    state.play_url = "https://example.com/demo.mp4"
    state.current_view = "player"
    assert build_app_view(state, handlers) is not None
