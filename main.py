import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import flet as ft

from app.core.state import AppState
from app.platform import is_mobile
from app.ui.views import build_app_view

APP_TITLE = "短剧移动版（框架测试）"


def main(page: ft.Page) -> None:
    page.title = APP_TITLE
    if not is_mobile():
        try:
            page.window.width = 400
            page.window.height = 820
        except Exception:  # noqa: BLE001
            pass

    from app import settings

    state = AppState()
    state.stream_base = settings.stream_base()
    handlers: dict = {}

    def rerender() -> None:
        page.controls.clear()
        page.add(build_app_view(state, handlers, page))
        page.update()

    def on_search() -> None:
        state.error_message = ""
        try:
            from app.services.search_service import search_dramas
            state.search_results = search_dramas(state.keyword)
        except Exception:  # noqa: BLE001
            from app.services.mock_service import search as mock_search
            state.search_results = mock_search(state.keyword)
            state.error_message = "源站搜索失败，已显示测试数据"
        state.current_view = "home"
        rerender()

    def on_open_detail(series_id) -> None:
        drama = None
        state.error_message = ""
        try:
            from app.services.detail_service import get_drama
            drama = get_drama(str(series_id))
        except Exception:  # noqa: BLE001
            drama = None
        if not drama:
            from app.services.mock_service import get_drama as mock_get_drama
            drama = mock_get_drama(str(series_id))
            if drama:
                state.error_message = "源站详情失败，已显示测试数据"
        if not drama:
            return
        state.current_drama = drama
        state.current_view = "detail"
        rerender()

    def on_back(e=None) -> None:
        state.current_view = "home"
        rerender()

    def on_play(episode: int, vid: str) -> None:
        from app.services.playback_service import resolve_play_url
        state.play_title = f"第{episode}集"
        state.play_url = resolve_play_url(vid) or ""
        state.error_message = "" if state.play_url else "无法解析播放地址"
        state.current_view = "player"
        rerender()

    handlers.update(
        {
            "rerender": rerender,
            "on_search": on_search,
            "on_open_detail": on_open_detail,
            "on_back": on_back,
            "on_play": on_play,
        }
    )

    page.add(build_app_view(state, handlers, page))


def run() -> None:
    ft.run(main, view=ft.AppView.FLET_APP)


if __name__ == "__main__":
    run()
