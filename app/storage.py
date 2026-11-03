import os


def data_dir() -> str:
    """应用私有可写目录（Android 打包运行时由 Flet 注入）。"""
    base = (os.getenv("FLET_APP_STORAGE_DATA") or "").strip()
    if base:
        return base
    return os.path.join(os.getcwd(), ".data")


def cache_dir() -> str:
    return os.path.join(data_dir(), "cache")
