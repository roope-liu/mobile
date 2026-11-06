import flet as ft

from app import settings
from app.services import cache_service, history_service


def settings_view(state, handlers, page=None):
    stream_field = ft.TextField(
        value=settings.stream_base(),
        label="播放代理地址",
        hint_text="流代理隧道地址（可选）",
        keyboard_type=ft.KeyboardType.URL,
        expand=True,
    )
    save_label = ft.Text("保存", color="#2F80ED")

    def save_stream(e):
        value = (stream_field.value or "").strip().rstrip("/")
        settings.set_stream_base(value)
        state.stream_base = value
        save_label.value = "已保存"
        save_label.update()

    def check_engine(e):
        from app.services.ondevice import diagnose_engine, find_ffmpeg

        diag.value = diagnose_engine()
        diag.color = ft.Colors.GREEN if find_ffmpeg() else ft.Colors.ORANGE
        diag.update()

    diag = ft.Text("", size=11, selectable=True, color="#7E8CA0")
    prefetch = ft.Dropdown(
        label="播放时预缓存后续集数",
        value=str(settings.prefetch_count()),
        options=[ft.dropdown.Option(key=str(i), text=f"{i} 集" if i else "关闭") for i in range(6)],
        on_select=lambda e: handlers["on_set_prefetch"](int(e.control.value)),
    )

    summary = cache_service.summary()
    cache_summary = ft.Text(
        f"成片 {summary['videos']} 个 · {cache_service.human_size(summary['video_bytes'])}；"
        f"临时文件 {summary['temp_files']} 个 · {cache_service.human_size(summary['temp_bytes'])}",
        size=12,
        color="#718198",
    )
    drama_rows = []
    for item in cache_service.drama_summary():
        name = item["name"]
        drama_rows.append(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(name, size=13, weight=ft.FontWeight.W_600, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(f"{item['count']} 集 · {cache_service.human_size(item['bytes'])}",
                                    size=11, color="#8795A8"),
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    ft.TextButton(
                        "清除此剧",
                        on_click=lambda e, n=name: handlers["on_clear_cache_drama"](n),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    if not drama_rows:
        drama_rows.append(ft.Text("暂无本地播放缓存", size=12, color="#8795A8"))

    history_items = history_service.list_entries()
    history_rows = []
    for item in history_items:
        history_rows.append(
            ft.Container(
                content=ft.ListTile(
                    leading=(
                        ft.Image(src=item.get("cover"), width=48, height=64, fit=ft.BoxFit.COVER)
                        if item.get("cover")
                        else ft.Icon(ft.Icons.LOCAL_MOVIES, color="#9FB0C6")
                    ),
                    title=ft.Text(item.get("series_name") or "未命名短剧", max_lines=1,
                                  overflow=ft.TextOverflow.ELLIPSIS),
                    subtitle=ft.Text(
                        f"第{item.get('episode') or 1}集 · {history_service.progress_text(item)}",
                        size=11,
                    ),
                    trailing=ft.Icon(ft.Icons.PLAY_ARROW, color="#2F80ED"),
                    on_click=lambda e, entry=item: handlers["on_resume"](entry),
                ),
                bgcolor="#F7FAFE",
                border_radius=12,
            )
        )
    if not history_rows:
        history_rows.append(ft.Text("暂无播放历史", size=12, color="#8795A8"))

    clear_history_toggle = ft.Checkbox(
        label="同时清除本地缓存及临时文件",
        value=False,
    )

    def confirm_clear_history(e):
        handlers["on_clear_history"](bool(clear_history_toggle.value))

    content = ft.Column(
        [
            ft.Container(
                content=ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=handlers["on_back"]),
                        ft.Text("设置", size=20, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=8,
                ),
                bgcolor="#FFFFFF",
                border_radius=14,
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row([ft.Icon(ft.Icons.LINK, color="#2F80ED"),
                                ft.Text("播放连接设置", size=16, weight=ft.FontWeight.BOLD)], spacing=8),
                        ft.Text("优先使用手机本地解码；本地引擎不可用时可配置代理。",
                                size=12, color="#7E8CA0"),
                        ft.Row([stream_field, ft.TextButton(content=save_label, on_click=save_stream)]),
                        ft.TextButton("检测本地解码引擎", icon=ft.Icons.MEMORY,
                                      on_click=check_engine),
                        diag,
                        ft.Divider(height=1),
                        prefetch,
                        ft.Text("预缓存会在当前集完成后，在后台并发下载后续集数；网络和存储空间充足时使用。",
                                size=11, color="#8795A8"),
                    ],
                    spacing=10,
                ),
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8EDF5"),
                border_radius=16,
                padding=16,
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row([ft.Icon(ft.Icons.DOWNLOAD_FOR_OFFLINE, color="#2F80ED"),
                                ft.Text("缓存管理", size=16, weight=ft.FontWeight.BOLD)], spacing=8),
                        cache_summary,
                        ft.TextButton("清除所有缓存和临时文件", icon=ft.Icons.DELETE_OUTLINE,
                                      style=ft.ButtonStyle(color="#C2413B"),
                                      on_click=handlers["on_clear_cache_all"]),
                        ft.Divider(height=1),
                        *drama_rows,
                    ],
                    spacing=8,
                ),
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8EDF5"),
                border_radius=16,
                padding=16,
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row([ft.Icon(ft.Icons.HISTORY, color="#2F80ED"),
                                ft.Text("播放历史", size=16, weight=ft.FontWeight.BOLD)], spacing=8),
                        *history_rows,
                        clear_history_toggle,
                        ft.TextButton("清除播放记录", icon=ft.Icons.DELETE_OUTLINE,
                                      style=ft.ButtonStyle(color="#C2413B"),
                                      on_click=confirm_clear_history),
                    ],
                    spacing=8,
                ),
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8EDF5"),
                border_radius=16,
                padding=16,
            ),
            ft.Text("仅供个人学习交流使用", size=11, color="#93A2B7",
                    text_align=ft.TextAlign.CENTER),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    return ft.Container(
        content=ft.SafeArea(content, expand=True),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=["#EEF4FD", "#F7FBFF"],
        ),
        expand=True,
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=10),
    )
