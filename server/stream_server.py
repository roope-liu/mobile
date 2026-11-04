"""本地流代理：GET /stream/<vid>.mp4

职责：解析 vid → 下载密文 → 解密(CENC) → ffmpeg mux → 支持 Range 返回。
运行在 PC 端，通过隧道暴露给手机；APP 只需把 STREAM_BASE 指向隧道地址。

环境变量：
- HOST / PORT            监听地址与端口（默认 0.0.0.0:8000）
- FFMPEG_PATH            ffmpeg 可执行文件路径（默认 PATH 中的 ffmpeg）
- STREAM_CACHE_DIR       缓存目录（默认 server/cache）
- STREAM_QUALITY         清晰度（best/worst/720p/1080p…）
"""
import os
import subprocess
import sys
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import video
from flask import Flask, abort, jsonify, send_file

CACHE_DIR = os.environ.get("STREAM_CACHE_DIR") or os.path.join(BASE_DIR, "cache")
FFMPEG = os.environ.get("FFMPEG_PATH") or "ffmpeg"
QUALITY = os.environ.get("STREAM_QUALITY", "best")

app = Flask(__name__)
_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for(vid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(vid, threading.Lock())


def _download(url: str, dest: str) -> None:
    import requests

    with requests.get(url, stream=True, timeout=(10, 120)) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def _decode_track(url: str, spade_a, enc_path: str, dec_path: str) -> str:
    _download(url, enc_path)
    if not spade_a:
        return enc_path
    video.decrypt_mp4(enc_path, video.unwrap_spade(spade_a), dec_path)
    return dec_path


def _build(vid: str, out_path: str) -> None:
    tracks = video.resolve_tracks(vid) or []
    vt = video.choose_track(tracks, QUALITY)
    if not vt or not vt.get("main_url"):
        raise RuntimeError("无可用视频轨")
    v_key = (vt.get("encrypt_info") or {}).get("spade_a")

    audio = video.resolve_audio_tracks(vid) or []
    a_url = audio[0].get("main_url") if audio else None
    a_key = (audio[0].get("encrypt_info") or {}).get("spade_a") if audio else None

    os.makedirs(CACHE_DIR, exist_ok=True)
    enc_v = out_path + ".v.enc"
    dec_v = out_path + ".v.dec"
    enc_a = out_path + ".a.enc"
    dec_a = out_path + ".a.dec"
    tmp = out_path + ".mux.tmp"
    cleanup = [enc_v, dec_v, enc_a, dec_a, tmp]
    try:
        v_path = _decode_track(vt["main_url"], v_key, enc_v, dec_v)
        a_path = _decode_track(a_url, a_key, enc_a, dec_a) if a_url else None

        cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", v_path]
        if a_path:
            cmd += ["-i", a_path]
        cmd += ["-c", "copy", "-tag:v", "hvc1", "-movflags", "+faststart", "-f", "mp4", tmp]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise RuntimeError(f"ffmpeg mux 失败：{result.stderr[:300]}")
        os.replace(tmp, out_path)
    finally:
        for p in cleanup:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


def _ensure(vid: str) -> str:
    out_path = os.path.join(CACHE_DIR, f"{vid}.mp4")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    with _lock_for(vid):
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        _build(vid, out_path)
    return out_path


@app.get("/healthz")
def healthz():
    return jsonify(ok=True)


@app.get("/stream/<vid>.mp4")
def stream(vid: str):
    vid = (vid or "").strip()
    if not vid.isdigit() or len(vid) < 10:
        abort(400, description="vid 非法")
    try:
        path = _ensure(vid)
    except Exception as exc:  # noqa: BLE001
        abort(502, description=str(exc))
    return send_file(path, mimetype="video/mp4", conditional=True)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    app.run(host=host, port=port, threaded=True)
