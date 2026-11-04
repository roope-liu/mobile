import flet as ft
import flet_video as ft_video

from app import settings


def _episode_columns(page) -> int:
    width = getattr(page, "width", None) or 400
    if width < 400:
        return 4
    if width < 700:
        return 6
    return 8


def home_view(state, handlers, page=None):
    tf = ft.TextField(
        value=state.keyword,
        hint_text="搜索短剧",
        on_change=lambda e: setattr(state, "keyword", e.control.value),
        on_submit=lambda e: handlers["on_search"](),
        expand=True,
    )
    search_btn = ft.IconButton(icon=ft.Icons.SEARCH, on_click=lambda e: handlers["on_search"]())

    cards = []
    for d in (state.search_results or []):
        cards.append(
            ft.Card(
                content=ft.ListTile(
                    title=ft.Text(d["series_name"]),
                    subtitle=ft.Text(f"{d['episode_cnt']} 集"),
                    on_click=lambda e, sid=d["series_id"]: handlers["on_open_detail"](sid),
                )
            )
        )

    stream_field = ft.TextField(
        value=state.stream_base,
        hint_text="流代理隧道地址（可选）",
        label="播放代理地址",
        keyboard_type=ft.KeyboardType.URL,
        expand=True,
    )

    def save_stream_base(e):
        state.stream_base = (stream_field.value or "").strip().rstrip("/")
        settings.set_stream_base(state.stream_base)
        try:
            e.control.content = "已保存"
            e.control.update()
        except Exception:  # noqa: BLE001
            pass

    settings_panel = ft.ExpansionTile(
        title=ft.Text("播放连接设置"),
        controls=[
            ft.Text("填入你创建的 HTTPS 隧道地址，例如 https://xxxx.example-tunnel.com；不填则播放演示视频。", size=12, color=ft.Colors.GREY),
            ft.Row([
                stream_field,
                ft.TextButton("保存", on_click=save_stream_base),
            ]),
        ],
    )

    body = ft.Column(
        [
            ft.Row([tf, search_btn]),
            settings_panel,
            ft.Text(
                f"共 {len(cards)} 条结果" if cards else "输入关键词搜索（真实源站搜索）",
                size=12,
                color=ft.Colors.GREY,
            ),
            ft.Column(cards, scroll=ft.ScrollMode.AUTO, expand=True, spacing=6),
        ],
        expand=True,
        spacing=8,
    )
    return ft.SafeArea(body, expand=True)


def detail_view(state, handlers, page=None):
    d = state.current_drama
    if not d:
        return ft.SafeArea(ft.Text("无数据"))

    episodes = list(d.get("vid_list") or [])
    eps = []
    for i, vid in enumerate(episodes, start=1):
        eps.append(
            ft.OutlinedButton(
                content=f"第{i}集",
                on_click=lambda e, ep=i, v=vid: handlers["on_play"](ep, v),
            )
        )

    grid = ft.Row(eps, wrap=True, spacing=8, run_spacing=8)

    body = ft.Column(
        [
            ft.Row(
                [
                    ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=handlers["on_back"]),
                    ft.Text(d["series_name"], size=18, weight=ft.FontWeight.BOLD),
                ]
            ),
            ft.Text(f"{len(episodes)} 集", size=12, color=ft.Colors.GREY),
            grid,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=8,
    )
    return ft.SafeArea(body, expand=True)


def player_view(state, handlers, page=None):
    playlist = []
    if state.play_url:
        playlist.append(ft_video.types.VideoMedia(resource=state.play_url))

    status = ft.Text(state.error_message or "", size=12, color=ft.Colors.RED, selectable=True)

    def _set_status(text: str) -> None:
        try:
            status.value = text
            status.update()
        except Exception:  # noqa: BLE001
            pass

    def _on_error(e) -> None:
        _set_status(f"播放错误：{getattr(e, 'data', '')}")

    def _on_load(e) -> None:
        _set_status("")

    video = ft_video.Video(
        playlist=playlist,
        autoplay=True,
        fit=ft.BoxFit.CONTAIN,
        expand=True,
        wakelock=True,
        on_error=_on_error,
        on_load=_on_load,
    )

    body = ft.Column(
        [
            ft.Row(
                [
                    ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=handlers["on_back"]),
                    ft.Text(state.play_title or "播放", size=16, weight=ft.FontWeight.BOLD),
                ]
            ),
            status,
            ft.Container(content=video, expand=True, bgcolor=ft.Colors.BLACK),
        ],
        expand=True,
        spacing=8,
    )
    return ft.SafeArea(body, expand=True)


def build_app_view(state, handlers, page=None):
    if state.current_view == "detail":
        return detail_view(state, handlers, page)
    if state.current_view == "player":
        return player_view(state, handlers, page)
    return home_view(state, handlers, page)
