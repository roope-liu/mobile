import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import flet as ft

APP_TITLE = "短剧移动版（框架测试）"


def main(page: ft.Page) -> None:
    try:
        _main(page)
    except Exception:  # noqa: BLE001
        try:
            page.controls.clear()
            page.add(
                ft.Text(
                    "启动失败，请把下面的信息发给开发者：\n\n" + traceback.format_exc(),
                    size=12,
                    selectable=True,
                )
            )
            page.update()
        except Exception:  # noqa: BLE001
            pass


def _main(page: ft.Page) -> None:
    from app.core.state import AppState
    from app.platform import is_mobile
    from app.ui.views import build_app_view

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

        from app.services.ondevice import find_ffmpeg, local_video_path
        from app.services.playback_service import prepare_stream, stream_base

        vids = drama.get("vid_list") or []
        if not vids:
            return
        if find_ffmpeg():
            vid = vids[0]

            def prefetch():
                try:
                    local_video_path(vid)
                except Exception:  # noqa: BLE001
                    pass

            page.run_thread(prefetch)
        elif stream_base():
            page.run_thread(lambda: prepare_stream(vids[0]))

    def on_back(e=None) -> None:
        state.current_view = "home"
        rerender()

    def on_play(episode: int, vid: str) -> None:
        from pathlib import Path

        from app.services.ondevice import describe_streams, find_ffmpeg, local_video_path
        from app.services.playback_service import prepare_stream, resolve_play_url, stream_base

        state.play_title = f"第{episode}集"
        state.play_url = ""
        state.error_message = ""
        state.loading_message = ""
        state.play_info = ""

        if find_ffmpeg():
            state.current_view = "loading"
            state.loading_message = f"正在下载并解密第{episode}集（首次约 20MB）…"
            rerender()

            def play_fallback(reason: str) -> None:
                state.error_message = reason
                state.play_url = resolve_play_url(vid) or ""
                if stream_base():
                    state.current_view = "loading"
                    state.loading_message = "本地播放失败，正在请求流代理准备视频…"
                    rerender()

                    def prepare_fallback():
                        ready = prepare_stream(vid)
                        state.loading_message = ""
                        if not ready:
                            state.error_message = (state.error_message + " 流代理准备也失败了。").strip()
                        state.current_view = "player"
                        rerender()

                    page.run_thread(prepare_fallback)
                else:
                    state.loading_message = ""
                    state.current_view = "player"
                    rerender()

            def play_local():
                try:
                    path = local_video_path(vid)
                    state.play_url = Path(path).as_uri()
                    state.play_info = describe_streams(path, find_ffmpeg() or "")
                    state.loading_message = ""
                    state.current_view = "player"
                    rerender()
                except Exception as exc:  # noqa: BLE001
                    play_fallback(f"本地播放失败：{str(exc)[:220]}")

            page.run_thread(play_local)
            return

        state.play_url = resolve_play_url(vid) or ""

        if stream_base():
            state.current_view = "loading"
            state.loading_message = "正在请求流代理准备视频…"
            rerender()

            def prepare():
                ready = prepare_stream(vid)
                if ready:
                    state.loading_message = ""
                    state.current_view = "player"
                else:
                    state.error_message = "流代理准备视频失败或超时；请检查隧道和代理服务。"
                    state.loading_message = ""
                    state.current_view = "player"
                rerender()

            page.run_thread(prepare)
            return

        state.error_message = ""
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
