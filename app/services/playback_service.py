"""播放来源提供者：阶段一只返回“可播 URL”。

- 配了 STREAM_BASE：走服务端流代理（A 方案）
- 未配置：回退到公开演示视频，用于验证 flet_video 的播放/全屏能力
阶段二会在此处切换为设备端解密+mux 生成的本地文件路径。
"""
from app.config import STREAM_BASE

# 演示视频候选（均为 H.264 + AAC 的 MP4，Android ExoPlayer 可直接硬解）
# 第一个为国内 CDN，避免海外地址加载失败或极慢
DEMO_URLS = (
    "https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/xgplayer_doc_video/mp4/xgplayer-demo-720p.mp4",
    "https://vjs.zencdn.net/v/oceans.mp4",
    "https://media.w3.org/2010/05/sintel/trailer.mp4",
)

DEMO_URL = DEMO_URLS[0]


def resolve_play_url(vid: str, quality: str = "best") -> str | None:
    vid = (vid or "").strip() if isinstance(vid, str) else str(vid).strip()
    if not vid:
        return None
    if STREAM_BASE:
        return f"{STREAM_BASE}/{vid}.mp4"
    return DEMO_URL
