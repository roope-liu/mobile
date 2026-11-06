"""应用设置：持久化到应用私有目录，供运行时修改而不必重打包。"""
import json
import os

from app.storage import data_dir

_DEFAULT = {"stream_base": "", "prefetch_count": "2"}


def _path() -> str:
    return os.path.join(data_dir(), "settings.json")


def load() -> dict:
    data = dict(_DEFAULT)
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            data.update({k: saved.get(k, v) for k, v in _DEFAULT.items()})
    except (OSError, ValueError):
        pass
    return data


def save(**kwargs) -> None:
    data = load()
    data.update({k: v for k, v in kwargs.items() if k in _DEFAULT})
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def stream_base() -> str:
    return str(load().get("stream_base") or "").strip().rstrip("/")


def set_stream_base(url: str) -> None:
    save(stream_base=str(url or "").strip().rstrip("/"))


def prefetch_count() -> int:
    try:
        return max(0, min(5, int(load().get("prefetch_count") or 0)))
    except (TypeError, ValueError):
        return 0


def set_prefetch_count(count: int) -> None:
    try:
        value = max(0, min(5, int(count)))
    except (TypeError, ValueError):
        value = 0
    save(prefetch_count=str(value))
