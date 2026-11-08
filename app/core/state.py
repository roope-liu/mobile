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
    loading_progress: int = 0
    play_info: str = ""
    play_series_id: str = ""
    play_episode: int = 0
    play_vid: str = ""
    resume_ms: int = 0
    last_position_ms: int = 0
    last_duration_ms: int = 0
