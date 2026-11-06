"""本地播放缓存管理：成片视频、临时文件与剧目索引。"""
import json
import os
import time

from app.storage import data_dir

_INDEX_NAME = "cache_index.json"
_UNKNOWN_NAME = "未知剧名（旧缓存）"
_TEMP_SUFFIXES = (".enc", ".dec", ".tmp")


def videos_dir() -> str:
    path = os.path.join(data_dir(), "videos")
    os.makedirs(path, exist_ok=True)
    return path


def _index_path() -> str:
    return os.path.join(data_dir(), _INDEX_NAME)


def load_index() -> dict:
    try:
        with open(_index_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_index(index: dict) -> None:
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(_index_path(), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def record(vid: str, name: str = "", episode: int = 0) -> None:
    vid = str(vid or "").strip()
    if not vid:
        return
    index = load_index()
    old = index.get(vid) or {}
    index[vid] = {
        "name": (name or old.get("name") or "").strip(),
        "episode": int(episode or old.get("episode") or 0),
        "ts": int(time.time()),
    }
    save_index(index)


def final_path(vid: str) -> str:
    return os.path.join(videos_dir(), f"{vid}.v2.mp4")


def is_cached(vid: str) -> bool:
    path = final_path(vid)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _vid_from_filename(name: str) -> str:
    if name.endswith(".v2.mp4"):
        return name[: -len(".v2.mp4")]
    return ""


def _iter_cache_files():
    """产出 (文件名, 路径, 是否成片, vid)。"""
    directory = videos_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        if name.endswith(".v2.mp4"):
            yield name, path, True, _vid_from_filename(name)
        elif name.endswith(_TEMP_SUFFIXES):
            yield name, path, False, name.split(".v2.mp4", 1)[0]


def summary() -> dict:
    videos = 0
    video_bytes = 0
    temp_files = 0
    temp_bytes = 0
    for _name, path, is_final, _vid in _iter_cache_files():
        size = _file_size(path)
        if is_final:
            videos += 1
            video_bytes += size
        else:
            temp_files += 1
            temp_bytes += size
    return {
        "videos": videos,
        "video_bytes": video_bytes,
        "temp_files": temp_files,
        "temp_bytes": temp_bytes,
        "total_bytes": video_bytes + temp_bytes,
    }


def drama_summary() -> list:
    """按剧名汇总缓存，返回 [{name, count, bytes}]，按占用空间降序。"""
    index = load_index()
    groups: dict = {}
    for _name, path, is_final, vid in _iter_cache_files():
        if not is_final:
            continue
        meta = index.get(vid) or {}
        name = str(meta.get("name") or "").strip() or _UNKNOWN_NAME
        item = groups.setdefault(name, {"name": name, "count": 0, "bytes": 0})
        item["count"] += 1
        item["bytes"] += _file_size(path)
    return sorted(groups.values(), key=lambda x: x["bytes"], reverse=True)


def clear_all() -> dict:
    """删除全部缓存与临时文件，重置索引。"""
    removed = 0
    freed = 0
    for _name, path, _is_final, _vid in list(_iter_cache_files()):
        freed += _file_size(path)
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    save_index({})
    return {"removed": removed, "bytes": freed}


def _remove_vid_files(vid: str) -> tuple:
    removed = 0
    freed = 0
    directory = videos_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        return removed, freed
    for name in names:
        if not name.startswith(f"{vid}."):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        freed += _file_size(path)
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed, freed


def clear_drama(name: str) -> dict:
    """按剧名删除对应剧集缓存（含其临时文件）。"""
    target = str(name or "").strip()
    index = load_index()
    vids = set()
    for _name, _path, _is_final, vid in _iter_cache_files():
        meta = index.get(vid) or {}
        meta_name = str(meta.get("name") or "").strip() or _UNKNOWN_NAME
        if meta_name == target and vid:
            vids.add(vid)
    removed = 0
    freed = 0
    for vid in vids:
        count, size = _remove_vid_files(vid)
        removed += count
        freed += size
        index.pop(vid, None)
    save_index(index)
    return {"removed": removed, "bytes": freed}


def human_size(num: int) -> str:
    size = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"
