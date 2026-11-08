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
    try:
        page.theme_mode = ft.ThemeMode.LIGHT
        page.bgcolor = "#EEF4FD"
    except Exception:  # noqa: BLE001
        pass
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
        state.play_token += 1
        state.error_message = ""
        try:
            from app.services.search_service import search_dramas
            state.search_results = search_dramas(state.keyword)
        except Exception as exc:  # noqa: BLE001
            from app.services.mock_service import search as mock_search
            state.search_results = mock_search(state.keyword)
            state.error_message = f"源站搜索失败：{str(exc)[:180]}（已显示测试数据）"
        state.current_view = "home"
        rerender()

    def on_open_detail(series_id) -> None:
        state.play_token += 1
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
                    local_video_path(
                        vid,
                        series_name=str(drama.get("series_name") or ""),
                        episode=1,
                    )
                except Exception:  # noqa: BLE001
                    pass

            page.run_thread(prefetch)
        elif stream_base():
            page.run_thread(lambda: prepare_stream(vids[0]))

    def on_back(e=None) -> None:
        state.play_token += 1
        if state.current_view in ("player", "loading") and state.current_drama:
            state.current_view = "detail"
        else:
            state.current_view = "home"
        rerender()

    def on_play(episode: int, vid: str) -> None:
        from pathlib import Path

        from app.services import history_service, prefetch_service
        from app.services.ondevice import describe_streams, find_ffmpeg, local_video_path
        from app.services.playback_service import prepare_stream, resolve_play_url, stream_base

        state.play_title = f"第{episode}集"
        state.play_url = ""
        state.play_token += 1
        token = state.play_token
        state.error_message = ""
        state.loading_message = ""
        state.loading_progress = 0
        state.play_info = ""
        state.play_episode = int(episode)
        state.play_vid = str(vid or "")
        state.play_series_id = ""

        drama = state.current_drama or {}
        series_id = str(drama.get("series_id") or "")
        series_name = str(drama.get("series_name") or "")
        cover = str(drama.get("series_cover") or drama.get("cover") or "")
        vid_list = [str(v) for v in (drama.get("vid_list") or [])]
        state.play_series_id = series_id

        previous = history_service.get(series_id) if series_id else None
        state.resume_ms = 0
        state.last_duration_ms = 0
        if previous and str(previous.get("vid") or "") == str(vid):
            position = int(previous.get("position_ms") or 0)
            duration = int(previous.get("duration_ms") or 0)
            if position > 1000 and not (duration and position >= duration - 10000):
                state.resume_ms = position
                state.last_duration_ms = duration
        state.last_position_ms = state.resume_ms
        history_service.upsert(
            series_id, series_name, cover, episode, vid, vid_list,
            position_ms=state.resume_ms,
        )

        def prefetch_next() -> None:
            count = settings.prefetch_count()
            if count > 0 and vid_list:
                prefetch_service.prefetch_upcoming(vid_list, episode, count, series_name)

        if find_ffmpeg():
            state.current_view = "loading"
            state.loading_message = f"正在准备第{episode}集…"
            state.loading_progress = 0
            rerender()

            def play_fallback(reason: str) -> None:
                if token != state.play_token:
                    return
                state.error_message = reason
                state.play_url = resolve_play_url(vid) or ""
                if stream_base():
                    state.current_view = "loading"
                    state.loading_message = "本地播放失败，正在请求流代理准备视频…"
                    rerender()

                    def prepare_fallback():
                        ready = prepare_stream(vid)
                        if token != state.play_token:
                            return
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

            def on_progress(percent: int, text: str) -> None:
                if token != state.play_token:
                    return
                state.loading_progress = int(percent)
                state.loading_message = text

            def play_local():
                try:
                    path = local_video_path(
                        vid, series_name=series_name, episode=episode,
                        progress_cb=on_progress,
                    )
                    if token != state.play_token:
                        return
                    state.play_url = Path(path).as_uri()
                    state.play_info = describe_streams(path, find_ffmpeg() or "")
                    state.loading_message = ""
                    state.current_view = "player"
                    rerender()
                    prefetch_next()
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
                if token != state.play_token:
                    return
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
        try:
            from app.platform import is_mobile

            if is_mobile():
                state.error_message = (
                    "未找到可执行的本地解码引擎：Android 10+ 禁止直接执行应用数据目录中的程序。"
                    "请安装启用 native 库解压的新版本，或在设置中配置播放代理。"
                )
        except Exception:  # noqa: BLE001
            pass
        state.current_view = "player"
        rerender()

    def on_open_settings(e=None) -> None:
        state.play_token += 1
        state.current_view = "settings"
        rerender()

    def on_resume(entry: dict) -> None:
        from app.services import history_service

        item = dict(entry or {})
        vid = str(item.get("vid") or "").strip()
        episode = int(item.get("episode") or 1)
        vid_list = [str(v) for v in (item.get("vid_list") or [])]
        if not vid and 0 < episode <= len(vid_list):
            vid = vid_list[episode - 1]
        if not vid:
            return
        state.current_drama = {
            "series_id": str(item.get("series_id") or ""),
            "series_name": str(item.get("series_name") or ""),
            "series_cover": str(item.get("cover") or ""),
            "series_intro": "",
            "tags": [],
            "vid_list": vid_list,
            "episode_cnt": len(vid_list),
        }
        on_play(episode, vid)

    def on_play_next(e=None) -> None:
        if state.current_view != "player":
            return
        drama = state.current_drama or {}
        vids = [str(v) for v in (drama.get("vid_list") or [])]
        episode = int(state.play_episode or 0)
        if 0 < episode < len(vids):
            on_play(episode + 1, vids[episode])

    def on_clear_cache_all(e=None) -> None:
        from app.services import cache_service

        cache_service.clear_all()
        rerender()

    def on_clear_cache_drama(name: str, e=None) -> None:
        from app.services import cache_service

        cache_service.clear_drama(name)
        rerender()

    def on_clear_history(also_cache: bool = False, e=None) -> None:
        from app.services import cache_service, history_service

        history_service.clear()
        if also_cache:
            cache_service.clear_all()
        rerender()

    def on_set_prefetch(count: int, e=None) -> None:
        settings.set_prefetch_count(count)
        rerender()

    handlers.update(
        {
            "rerender": rerender,
            "on_search": on_search,
            "on_open_detail": on_open_detail,
            "on_back": on_back,
            "on_play": on_play,
            "on_open_settings": on_open_settings,
            "on_resume": on_resume,
            "on_play_next": on_play_next,
            "on_clear_cache_all": on_clear_cache_all,
            "on_clear_cache_drama": on_clear_cache_drama,
            "on_clear_history": on_clear_history,
            "on_set_prefetch": on_set_prefetch,
        }
    )

    page.add(build_app_view(state, handlers, page))


def run() -> None:
    ft.run(main, view=ft.AppView.FLET_APP)


if __name__ == "__main__":
    run()
