"""播放来源提供者：阶段一只返回“可播 URL”。

- 配了 STREAM_BASE：走服务端流代理（A 方案）
- 未配置：回退演示视频，用于验证 flet_video 的播放/全屏能力
阶段二会在此处切换为设备端解密+mux 生成的本地文件路径。
"""
from app.config import STREAM_BASE

DEMO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"


def resolve_play_url(vid: str, quality: str = "best") -> str | None:
    vid = (vid or "").strip() if isinstance(vid, str) else str(vid).strip()
    if not vid:
        return None
    if STREAM_BASE:
        return f"{STREAM_BASE}/{vid}.mp4"
    return DEMO_URL
