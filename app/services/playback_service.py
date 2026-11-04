"""播放来源提供者：阶段一只返回“可播 URL”。

播放地址优先级：
1. 环境变量 STREAM_BASE
2. 应用内设置（首页“设置”里填写的隧道地址）
3. 回退演示视频（仅用于播放器验证）
阶段二会在此处切换为设备端解密+mux 生成的本地文件路径。
"""
import os

from app import settings

# 演示视频候选（均为 H.264 + AAC 的 MP4，Android ExoPlayer 可直接硬解）
DEMO_URLS = (
    "https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/xgplayer_doc_video/mp4/xgplayer-demo-720p.mp4",
    "https://vjs.zencdn.net/v/oceans.mp4",
    "https://media.w3.org/2010/05/sintel/trailer.mp4",
)

DEMO_URL = DEMO_URLS[0]


def stream_base() -> str:
    env = (os.getenv("STREAM_BASE") or "").strip().rstrip("/")
    return env or settings.stream_base()


def prepare_stream(vid: str, timeout: int = 240) -> bool:
    """请求流代理在后台准备（下载/解密/mux），轮询直到就绪。"""
    base = stream_base()
    vid = str(vid or "").strip()
    if not base or not vid:
        return False

    import time

    import requests

    try:
        requests.get(f"{base}/prepare/{vid}.mp4", timeout=20)
    except Exception:  # noqa: BLE001
        pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{base}/status/{vid}.mp4", timeout=10)
            if resp.ok:
                data = resp.json()
                if data.get("ready"):
                    return True
                if data.get("state") == "error":
                    return False
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


def resolve_play_url(vid: str, quality: str = "best") -> str | None:
    vid = (vid or "").strip() if isinstance(vid, str) else str(vid).strip()
    if not vid:
        return None
    base = stream_base()
    if base:
        return f"{base}/{vid}.mp4"
    return DEMO_URL
