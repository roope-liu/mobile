import os


def is_mobile() -> bool:
    """当前是否运行在移动端（Android/iOS）打包环境。"""
    platform = (os.getenv("FLET_PLATFORM") or "").strip().lower()
    if platform in ("android", "ios"):
        return True
    return bool(os.getenv("FLET_APP_STORAGE_DATA"))


def is_android() -> bool:
    return (os.getenv("FLET_PLATFORM") or "").strip().lower() == "android"
