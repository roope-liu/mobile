from dataclasses import dataclass, field


@dataclass
class AppState:
    current_view: str = "home"
    keyword: str = ""
    search_results: list = field(default_factory=list)
    current_drama: dict | None = None
    play_title: str = ""
    play_url: str = ""
    error_message: str = ""
    stream_base: str = ""
    loading_message: str = ""
    play_info: str = ""
