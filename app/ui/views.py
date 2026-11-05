import flet as ft
import flet_video as ft_video

from app import settings


def _cover_url(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("series_cover", "cover", "horiz_cover", "cover_url", "thumb_url"):
        value = (item.get(key) or "").strip()
        if value:
            return value
    return ""


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
        cover = _cover_url(d)
        leading = (
            ft.Image(src=cover, width=56, height=76, fit=ft.BoxFit.COVER, border_radius=6)
            if cover
            else None
        )
        cards.append(
            ft.Card(
                content=ft.ListTile(
                    leading=leading,
                    title=ft.Text(d["series_name"]),
                    subtitle=ft.Text(
                        " · ".join(
                            part for part in (
                                f"{d['episode_cnt']} 集",
                                " / ".join(d.get("tags") or []),
                            ) if part
                        )
                    ),
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

    engine_status = ft.Text("", size=12, color=ft.Colors.GREY, selectable=True)

    def check_engine(e):
        from app.services.ondevice import diagnose_engine, find_ffmpeg

        engine_status.value = diagnose_engine()
        engine_status.color = ft.Colors.GREEN if find_ffmpeg() else ft.Colors.ORANGE
        try:
            engine_status.update()
        except Exception:  # noqa: BLE001
            pass

    settings_panel = ft.ExpansionTile(
        title=ft.Text("播放连接设置"),
        expanded=not bool(state.stream_base),
        controls=[
            ft.Text("优先使用手机本地解码；未检测到本地引擎时才使用下面的代理地址。", size=12, color=ft.Colors.GREY),
            ft.Row([
                stream_field,
                ft.TextButton("保存", on_click=save_stream_base),
            ]),
            ft.Row([
                ft.TextButton("检测本地解码引擎", on_click=check_engine),
                engine_status,
            ]),
        ],
    )

    body = ft.Column(
        [
            ft.Row([tf, search_btn]),
            ft.Text(state.error_message, size=12, color=ft.Colors.ORANGE)
            if state.error_message
            else ft.Container(height=0),
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

    cover = _cover_url(d)
    intro = (d.get("series_intro") or d.get("video_desc") or "").strip()
    tags = " / ".join(d.get("tags") or [])
    info_column = ft.Column(
        [
            ft.Text(d["series_name"], size=18, weight=ft.FontWeight.BOLD),
            ft.Text(f"{len(episodes)} 集" + (f" · {tags}" if tags else ""), size=12, color=ft.Colors.GREY),
            ft.Text(intro, size=12, max_lines=4, overflow=ft.TextOverflow.ELLIPSIS) if intro else ft.Container(height=0),
        ],
        expand=True,
        spacing=4,
    )
    header = ft.Row(
        [
            ft.Image(src=cover, width=96, height=132, fit=ft.BoxFit.COVER, border_radius=8)
            if cover else ft.Container(width=0),
            info_column,
        ],
        vertical_alignment=ft.CrossAxisAlignment.START,
        spacing=12,
    )

    body = ft.Column(
        [
            ft.Row(
                [
                    ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=handlers["on_back"]),
                    ft.Text("详情", size=16, weight=ft.FontWeight.BOLD),
                ]
            ),
            header,
            ft.Divider(),
            grid,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=8,
    )
    return ft.SafeArea(body, expand=True)


def player_view(state, handlers, page=None):
    from app.services.playback_service import stream_base

    playlist = []
    if state.play_url:
        playlist.append(ft_video.types.VideoMedia(resource=state.play_url))

    status = ft.Text(
        state.error_message or state.loading_message or "",
        size=12,
        color=ft.Colors.RED if state.error_message else ft.Colors.GREY,
        selectable=True,
    )
    demo_hint = (
        ft.Container(
            content=ft.Text(
                "未配置播放代理，当前播放的是演示视频。请在首页“播放连接设置”填入隧道地址后重试。",
                size=11,
                color=ft.Colors.ORANGE,
            ),
            padding=6,
        )
        if not stream_base()
        else ft.Container(height=0)
    )

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
            demo_hint,
            status,
            ft.Container(content=video, expand=True, bgcolor=ft.Colors.BLACK),
        ],
        expand=True,
        spacing=8,
    )
    return ft.SafeArea(body, expand=True)


def loading_view(state, handlers, page=None):
    return ft.SafeArea(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=handlers["on_back"]),
                        ft.Text(state.play_title or "加载中", size=16, weight=ft.FontWeight.BOLD),
                    ]
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.ProgressRing(),
                            ft.Text(state.loading_message or "正在准备视频…", size=13, color=ft.Colors.GREY),
                            ft.Text("首次播放需要在本机解密并合并音视频，通常 3~20 秒", size=11, color=ft.Colors.GREY),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                ),
            ],
            expand=True,
            spacing=8,
        ),
        expand=True,
    )


def build_app_view(state, handlers, page=None):
    if state.current_view == "loading":
        return loading_view(state, handlers, page)
    if state.current_view == "detail":
        return detail_view(state, handlers, page)
    if state.current_view == "player":
        return player_view(state, handlers, page)
    return home_view(state, handlers, page)
