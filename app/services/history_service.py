"""播放历史与断点记录。"""
import json
import os
import time

from app.storage import data_dir

_FILE_NAME = "history.json"


def _path() -> str:
    return os.path.join(data_dir(), _FILE_NAME)


def _load() -> dict:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"items": {}}


def _save(data: dict) -> None:
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def list_entries() -> list:
    items = list(((_load().get("items") or {}).values()))
    items = [item for item in items if isinstance(item, dict)]
    return sorted(items, key=lambda x: int(x.get("updated_ts") or 0), reverse=True)


def get(series_id: str) -> dict | None:
    series_id = str(series_id or "").strip()
    if not series_id:
        return None
    item = (_load().get("items") or {}).get(series_id)
    return item if isinstance(item, dict) else None


def upsert(series_id: str, series_name: str, cover: str = "", episode: int = 0,
           vid: str = "", vid_list: list | None = None,
           position_ms: int = 0, duration_ms: int = 0) -> None:
    series_id = str(series_id or "").strip()
    if not series_id:
        return
    data = _load()
    items = data.setdefault("items", {})
    old = items.get(series_id) or {}
    items[series_id] = {
        "series_id": series_id,
        "series_name": (series_name or old.get("series_name") or "").strip(),
        "cover": (cover or old.get("cover") or "").strip(),
        "episode": int(episode or old.get("episode") or 0),
        "vid": str(vid or old.get("vid") or ""),
        "vid_list": list(vid_list or old.get("vid_list") or []),
        "position_ms": int(position_ms or old.get("position_ms") or 0),
        "duration_ms": int(duration_ms or old.get("duration_ms") or 0),
        "updated_ts": int(time.time()),
    }
    _save(data)


def save_position(series_id: str, vid: str, position_ms: int,
                  duration_ms: int = 0) -> None:
    series_id = str(series_id or "").strip()
    if not series_id:
        return
    data = _load()
    items = data.setdefault("items", {})
    item = items.get(series_id)
    if not isinstance(item, dict):
        return
    if str(item.get("vid") or "") and str(vid or "") and str(item.get("vid")) != str(vid):
        return
    item["position_ms"] = max(0, int(position_ms or 0))
    if duration_ms:
        item["duration_ms"] = int(duration_ms)
    item["updated_ts"] = int(time.time())
    _save(data)


def clear() -> int:
    data = _load()
    count = len(data.get("items") or {})
    _save({"items": {}})
    return count


def progress_text(item: dict) -> str:
    pos = int(item.get("position_ms") or 0) // 1000
    dur = int(item.get("duration_ms") or 0) // 1000
    pos_text = f"{pos // 60:02d}:{pos % 60:02d}"
    if dur > 0:
        return f"看到 {pos_text} / {dur // 60:02d}:{dur % 60:02d}"
    return f"看到 {pos_text}" if pos > 0 else "未开始播放"
