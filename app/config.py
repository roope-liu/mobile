import os

from app.platform import is_mobile

# 阶段一：移动端关闭下载与缓存管理入口
ENABLE_DOWNLOAD = not is_mobile()
ENABLE_CACHE_MANAGER = not is_mobile()

# 播放来源：remote（服务端流代理/远程直链）或 local（设备端解密+mux，阶段二）
PLAYBACK_PROVIDER = "remote"

# 服务端流代理基址；为空时回退到演示视频，便于先验证 flet_video
STREAM_BASE = (os.getenv("STREAM_BASE") or "").strip().rstrip("/")
