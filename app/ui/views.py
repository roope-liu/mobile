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
    def on_quick_search(keyword: str) -> None:
        state.keyword = keyword
        handlers["on_search"]()

    search_field = ft.TextField(
        value=state.keyword,
        hint_text="剧名 / 演员 / 关键词",
        prefix_icon=ft.Icons.SEARCH,
        border=ft.NoInputBorder(),
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=16),
        on_change=lambda e: setattr(state, "keyword", e.control.value),
        on_submit=lambda e: handlers["on_search"](),
        expand=True,
    )
    search_btn = ft.FilledButton(
        content="搜索",
        icon=ft.Icons.SEARCH,
        on_click=lambda e: handlers["on_search"](),
        style=ft.ButtonStyle(bgcolor="#2F80ED", color=ft.Colors.WHITE),
    )

    cards = []
    for d in (state.search_results or []):
        cover = _cover_url(d)
        title = d.get("series_name") or "未命名短剧"
        tags = d.get("tags") or []
        episode_count = d.get("episode_cnt") or 0
        cards.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Container(
                            content=(
                                ft.Image(src=cover, fit=ft.BoxFit.COVER, expand=True)
                                if cover
                                else ft.Container(
                                    content=ft.Icon(ft.Icons.LOCAL_MOVIES, size=36, color="#9FB0C6"),
                                    bgcolor="#E8EEF7",
                                    alignment=ft.Alignment.CENTER,
                                    expand=True,
                                )
                            ),
                            height=184,
                            clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            border_radius=ft.BorderRadius.only(top_left=14, top_right=14),
                        ),
                        ft.Column(
                            [
                                ft.Text(title, size=14, weight=ft.FontWeight.BOLD, max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(
                                    f"{episode_count} 集" + (f" · {' / '.join(tags[:2])}" if tags else ""),
                                    size=11,
                                    color="#7E8CA0",
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=5,
                        ),
                    ],
                    spacing=9,
                ),
                padding=0,
                border_radius=14,
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8EDF5"),
                shadow=ft.BoxShadow(blur_radius=12, spread_radius=0, color="#100D2440", offset=ft.Offset(0, 4)),
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                on_click=lambda e, sid=d.get("series_id"): handlers["on_open_detail"](sid),
                col={"xs": 6, "sm": 4, "md": 3, "lg": 3},
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

    settings_panel = ft.Container(
        content=ft.ExpansionTile(
            title=ft.Row(
                [ft.Icon(ft.Icons.TUNE, size=18, color="#2F80ED"),
                 ft.Text("播放连接设置", size=14, weight=ft.FontWeight.W_600)],
                spacing=6,
            ),
            expanded=not bool(state.stream_base),
            controls_padding=ft.Padding.only(left=12, right=12, bottom=12),
            controls=[
                ft.Text("优先使用手机本地解码；未检测到本地引擎时才使用下面的代理地址。",
                        size=12, color="#7E8CA0"),
                ft.Row([
                    stream_field,
                    ft.TextButton("保存", on_click=save_stream_base),
                ]),
                ft.Row([
                    ft.TextButton("检测本地解码引擎", on_click=check_engine),
                ]),
                engine_status,
            ],
        ),
        bgcolor="#FFFFFF",
        border_radius=16,
        border=ft.Border.all(1, "#E8EDF5"),
        shadow=ft.BoxShadow(blur_radius=10, color="#0F1B3D66", offset=ft.Offset(0, 3)),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    def _chip(label: str, keyword: str):
        return ft.Container(
            content=ft.Text(label, size=12, color=ft.Colors.WHITE),
            bgcolor="#24FFFFFF",
            border=ft.Border.all(1, "#3DFFFFFF"),
            border_radius=999,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            on_click=lambda e: on_quick_search(keyword),
        )

    hero = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text("SHORT DRAMA BOX", size=10, color=ft.Colors.WHITE),
                    bgcolor="#24FFFFFF",
                    border=ft.Border.all(1, "#3DFFFFFF"),
                    border_radius=999,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=5),
                ),
                ft.Text("搜索你想看的短剧", size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Text("海量短剧 · 在线播放 · 本机解密 · 多端同步",
                        size=13, color="#C9DBF5"),
                ft.Container(
                    content=ft.Row(
                        [search_field, search_btn],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor="#F2F7FF",
                    border_radius=16,
                    padding=ft.Padding.only(left=6, right=6, top=4, bottom=4),
                    margin=ft.Margin.only(top=6),
                ),
                ft.Row(
                    [_chip("热门：闪婚", "闪婚"),
                     _chip("总裁", "总裁"),
                     _chip("重生", "重生"),
                     _chip("漫剧", "漫剧")],
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                ),
            ],
            spacing=10,
        ),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=["#102A5C", "#1F4F99", "#2F80ED"],
            stops=[0.0, 0.45, 1.0],
        ),
        border_radius=20,
        padding=22,
        shadow=ft.BoxShadow(blur_radius=26, color="#332F80ED", offset=ft.Offset(0, 10)),
    )

    def _placeholder_cards(label: str):
        return [
            ft.Container(
                width=104,
                content=ft.Column(
                    [
                        ft.Container(
                            height=132,
                            bgcolor="#EEF3FA",
                            border_radius=10,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(ft.Icons.MOVIE_OUTLINED, color="#A9B8CC", size=28),
                        ),
                        ft.Text("待推送", size=12, weight=ft.FontWeight.W_600, max_lines=1),
                        ft.Text(f"{label} · 占位", size=10, color="#8A99AD", max_lines=1),
                    ],
                    spacing=4,
                ),
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8EDF5"),
                border_radius=12,
                padding=8,
            )
            for _ in range(6)
        ]

    rec_body = ft.Row(_placeholder_cards("真人剧"), wrap=True, spacing=10, run_spacing=10)

    def _set_tab(label: str, chips: dict) -> None:
        rec_body.controls = _placeholder_cards(label)
        for key, chip in chips.items():
            selected = key == label
            chip.bgcolor = "#2F80ED" if selected else "#F2F7FF"
            chip.content.color = ft.Colors.WHITE if selected else "#5B6C82"
            chip.update()
        rec_body.update()

    rec_tabs: dict = {}
    tab_row = ft.Row([], spacing=8, wrap=True)
    for label in ("真人剧", "AI剧", "热门推荐"):
        chip = ft.Container(
            content=ft.Text(label, size=12),
            bgcolor="#2F80ED" if label == "真人剧" else "#F2F7FF",
            border_radius=999,
            padding=ft.Padding.symmetric(horizontal=14, vertical=7),
        )
        rec_tabs[label] = chip
        tab_row.controls.append(chip)

    for label, chip in rec_tabs.items():
        chip.on_click = (lambda e, lab=label: _set_tab(lab, rec_tabs))
    # 首次渲染时同步第一个 tab 的高亮
    for label, chip in rec_tabs.items():
        selected = label == "真人剧"
        chip.content.color = ft.Colors.WHITE if selected else "#5B6C82"

    recommend_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [ft.Container(width=4, height=18, bgcolor="#2F80ED", border_radius=999),
                             ft.Text("推荐内容", size=16, weight=ft.FontWeight.BOLD)],
                            spacing=8,
                        ),
                        ft.Container(expand=True),
                        tab_row,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                rec_body,
            ],
            spacing=12,
        ),
        bgcolor="#FFFFFF",
        border_radius=16,
        border=ft.Border.all(1, "#E8EDF5"),
        padding=16,
        shadow=ft.BoxShadow(blur_radius=10, color="#0F1B3D66", offset=ft.Offset(0, 3)),
    )

    results_section = (
        ft.ResponsiveRow(
            controls=cards,
            spacing=10,
            run_spacing=12,
        )
        if cards
        else ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SEARCH, size=32, color="#A9B8CC"),
                    ft.Text("输入关键词开始搜索真实源站短剧", size=13, color="#7E8CA0"),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            bgcolor="#FFFFFF",
            border=ft.Border.all(1, "#E8EDF5"),
            border_radius=16,
            padding=28,
            alignment=ft.Alignment.CENTER,
        )
    )

    navbar = ft.Container(
        content=ft.Row(
            [
                ft.Text("🎬 短剧盒子", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Container(expand=True),
                ft.Text("移动版", size=12, color="#D6E6FF"),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.CENTER_LEFT,
            end=ft.Alignment.CENTER_RIGHT,
            colors=["#2F80ED", "#56A8F5"],
        ),
        padding=ft.Padding.symmetric(horizontal=18, vertical=14),
        border_radius=14,
        shadow=ft.BoxShadow(blur_radius=14, color="#332F80ED", offset=ft.Offset(0, 4)),
    )

    results_header = ft.Row(
        [
            ft.Container(width=4, height=18, bgcolor="#FF8A3D", border_radius=999),
            ft.Text(
                f"搜索结果 · {len(cards)} 条" if cards else "搜索结果",
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
        ],
        spacing=8,
    )

    body = ft.Column(
        [
            navbar,
            hero,
            ft.Container(
                content=ft.Text(state.error_message, size=12, color="#B45309"),
                bgcolor="#FFF4E5",
                border_radius=12,
                padding=10,
            )
            if state.error_message
            else ft.Container(height=0),
            settings_panel,
            recommend_card,
            results_header,
            results_section,
            ft.Text("仅供个人学习交流使用", size=11, color="#93A2B7",
                    text_align=ft.TextAlign.CENTER),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    return ft.Container(
        content=ft.SafeArea(body, expand=True),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=["#EEF4FD", "#F7FBFF"],
        ),
        expand=True,
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=10),
    )


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

    hint = ""
    if not stream_base() and state.play_url and state.play_url.startswith("http"):
        hint = "未配置播放代理，当前播放的是演示视频。可在首页“播放连接设置”填入隧道地址。"

    status = ft.Text(
        state.error_message or state.loading_message or state.play_info or hint,
        size=12,
        color=ft.Colors.RED
        if state.error_message
        else (ft.Colors.ORANGE if (state.loading_message or hint) else ft.Colors.GREY),
        selectable=True,
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

    volume_icon = ft.Icon(ft.Icons.VOLUME_UP, color=ft.Colors.WHITE, size=22)
    volume_state = {"value": 100.0}
    volume_slider = ft.Slider(
        min=0,
        max=100,
        value=100,
        width=96,
        active_color=ft.Colors.WHITE,
        inactive_color="#66FFFFFF",
    )
    volume_button = ft.IconButton(icon=volume_icon, tooltip="静音/恢复")

    controls = ft_video.types.MaterialVideoControls(
        display_seek_bar=True,
        seek_gesture=True,
        volume_gesture=True,
        brightness_gesture=True,
        seek_on_double_tap=True,
        top_button_bar=[
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=ft.Colors.WHITE,
                tooltip="返回",
                on_click=handlers["on_back"],
            )
        ],
        bottom_button_bar=[
            ft_video.types.VideoPlayOrPauseButton(),
            ft_video.types.VideoSpacer(),
            ft_video.types.VideoPositionIndicator(),
            ft.Container(
                content=ft.Row(
                    [volume_button, volume_slider],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                height=40,
            ),
            ft_video.types.VideoFullscreenButton(),
        ],
        button_bar_button_size=30,
    )

    video = ft_video.Video(
        playlist=playlist,
        autoplay=True,
        fit=ft.BoxFit.CONTAIN,
        expand=True,
        wakelock=True,
        muted=False,
        volume=100,
        controls=controls,
        on_error=_on_error,
        on_load=_on_load,
    )

    def _apply_volume(value: float) -> None:
        volume_state["value"] = float(value)
        video.volume = float(value)
        video.muted = float(value) <= 0
        volume_icon.name = (
            ft.Icons.VOLUME_OFF
            if float(value) <= 0
            else (ft.Icons.VOLUME_DOWN if float(value) < 50 else ft.Icons.VOLUME_UP)
        )
        try:
            video.update()
            volume_icon.update()
        except Exception:  # noqa: BLE001
            pass

    def _on_volume_slider(e) -> None:
        _apply_volume(float(e.control.value))

    def _toggle_mute(e) -> None:
        _apply_volume(0 if volume_state["value"] > 0 else 100)
        volume_slider.value = volume_state["value"]
        try:
            volume_slider.update()
        except Exception:  # noqa: BLE001
            pass

    volume_slider.on_change = _on_volume_slider
    volume_button.on_click = _toggle_mute

    stack = ft.Stack(
        [
            ft.Container(content=video, expand=True, bgcolor=ft.Colors.BLACK),
            ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color=ft.Colors.WHITE,
                    bgcolor="#66000000",
                    on_click=handlers["on_back"],
                ),
                left=8,
                top=8,
            ),
            ft.Container(content=status, left=12, right=12, bottom=72),
        ],
        expand=True,
    )
    return ft.SafeArea(stack, expand=True)


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
