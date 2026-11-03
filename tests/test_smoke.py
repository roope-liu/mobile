"""框架冒烟测试：导入、平台开关与播放来源。"""
import os

os.environ.setdefault("STREAM_BASE", "")


def test_imports():
    import flet  # noqa: F401
    import flet_video  # noqa: F401
    from app.platform import is_mobile, is_android  # noqa: F401
    from app.config import ENABLE_DOWNLOAD, ENABLE_CACHE_MANAGER
    from app.storage import data_dir  # noqa: F401
    from app.services.playback_service import resolve_play_url
    assert ENABLE_DOWNLOAD is False or ENABLE_DOWNLOAD is True
    assert resolve_play_url("v1") is not None


def test_mock_search():
    from app.services.mock_service import search, get_drama
    res = search("框架")
    assert len(res) >= 1
    drama = get_drama(res[0]["series_id"])
    assert drama is not None
    assert drama["vid_list"]
