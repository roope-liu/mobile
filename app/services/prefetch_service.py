"""播放后续集数的后台预缓存（多线程）。"""
import threading

from concurrent.futures import ThreadPoolExecutor

from app.services import cache_service

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="prefetch")
_LOCK = threading.Lock()
_INFLIGHT: set = set()


def _run(vid: str, name: str, episode: int) -> None:
    try:
        from app.services.ondevice import local_video_path

        local_video_path(vid, series_name=name, episode=episode)
    except Exception:  # noqa: BLE001
        pass
    finally:
        with _LOCK:
            _INFLIGHT.discard(vid)


def warm(vid: str, name: str = "", episode: int = 0) -> None:
    vid = str(vid or "").strip()
    if not vid or cache_service.is_cached(vid):
        return
    with _LOCK:
        if vid in _INFLIGHT:
            return
        _INFLIGHT.add(vid)
    _EXECUTOR.submit(_run, vid, name, episode)


def prefetch_upcoming(vid_list: list, current_episode: int, count: int,
                      series_name: str = "") -> None:
    """当前集之后，最多预缓存 count 集。"""
    try:
        count = max(0, min(5, int(count)))
    except (TypeError, ValueError):
        return
    if count <= 0:
        return
    vids = [str(v) for v in (vid_list or [])]
    start = int(current_episode)  # 1 基集数，下一集索引即 start
    for index in range(start, min(len(vids), start + count)):
        warm(vids[index], series_name, index + 1)
