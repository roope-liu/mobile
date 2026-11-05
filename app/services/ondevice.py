"""手机端本地播放：下载 → 纯 Python AES-CTR 解密 → ffmpeg 重封装为 hvc1。"""
import os
import re
import struct
import subprocess
import sys

import requests

from app.services.aes_ctr import ctr_xor
from app.services.source_video import choose_track, resolve_tracks, unwrap_spade
from app.storage import data_dir

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------- MP4 解析（与 PC 端算法一致） ----------

def _ib(data, start, end):
    o = start
    while o + 8 <= end:
        size = struct.unpack(">I", data[o:o + 4])[0]
        box_type = data[o + 4:o + 8]
        header_size = 8
        if size == 1:
            size = struct.unpack(">Q", data[o + 8:o + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - o
        yield box_type, o, size, header_size
        o += size


def _find(data, path, start=0, end=None):
    if end is None:
        end = len(data)
    for box_type, o, size, header_size in _ib(data, start, end):
        if box_type == path[0]:
            if len(path) == 1:
                return (o + header_size, o + size)
            return _find(data, path[1:], o + header_size, o + size)
    return None


def _u32(data, offset):
    return struct.unpack(">I", data[offset:offset + 4])[0]


def _parse_track_samples(data, handler=b"vide"):
    moov = _find(data, [b"moov"])
    if not moov:
        return [], []
    traks = [(o + hs, o + sz) for t, o, sz, hs in _ib(data, *moov) if t == b"trak"]

    def hdlr(tr):
        h = _find(data, [b"mdia", b"hdlr"], *tr)
        return data[h[0] + 8:h[0] + 12] if h else None

    want = [t for t in traks if hdlr(t) == handler]
    if not want:
        return [], []
    s, e = _find(data, [b"mdia", b"minf", b"stbl"], *want[0])
    stsz = _find(data, [b"stsz"], s, e)
    stco = _find(data, [b"stco"], s, e)
    co64 = _find(data, [b"co64"], s, e)
    stsc = _find(data, [b"stsc"], s, e)
    if not all((stsz, stsc)) or (not stco and not co64):
        return [], []

    ss = _u32(data, stsz[0] + 4)
    cnt = _u32(data, stsz[0] + 8)
    sizes = [ss] * cnt if ss else [_u32(data, stsz[0] + 12 + 4 * i) for i in range(cnt)]
    if stco:
        n = _u32(data, stco[0] + 4)
        chunks = [_u32(data, stco[0] + 8 + 4 * i) for i in range(n)]
    else:
        n = _u32(data, co64[0] + 4)
        chunks = [struct.unpack(">Q", data[co64[0] + 8 + 8 * i:co64[0] + 16 + 8 * i])[0] for i in range(n)]
    ne = _u32(data, stsc[0] + 4)
    runs = [
        (_u32(data, stsc[0] + 8 + 12 * i), _u32(data, stsc[0] + 12 + 12 * i),
         _u32(data, stsc[0] + 16 + 12 * i))
        for i in range(ne)
    ]
    spc = [0] * len(chunks)
    for i, (first_chunk, samples_per_chunk, _) in enumerate(runs):
        last = runs[i + 1][0] - 1 if i + 1 < len(runs) else len(chunks)
        for c in range(first_chunk, last + 1):
            if 1 <= c <= len(chunks):
                spc[c - 1] = samples_per_chunk
    offsets = []
    si = 0
    for c in range(len(chunks)):
        off = chunks[c]
        for _ in range(spc[c]):
            if si >= cnt:
                break
            offsets.append(off)
            off += sizes[si]
            si += 1
    return sizes, offsets


def _trak_senc_iv8(data, lo, hi):
    for m in re.finditer(b"senc", data[lo:hi]):
        o = lo + m.start() + 8 + 4
        if o + 8 <= hi:
            return data[o:o + 8].hex()
    return None


def decrypt_mp4(enc_path, key_hex, out_path):
    data = open(enc_path, "rb").read()
    buf = bytearray(data)
    key = bytes.fromhex(key_hex)
    moov = _find(data, [b"moov"])
    if not moov:
        raise RuntimeError("密文无 moov 盒")
    for box_type, o, size, header_size in _ib(data, *moov):
        if box_type != b"trak":
            continue
        h = _find(data, [b"mdia", b"hdlr"], o + header_size, o + size)
        handler = data[h[0] + 8:h[0] + 12] if h else None
        if handler not in (b"vide", b"soun"):
            continue
        iv8 = _trak_senc_iv8(data, o, o + size)
        if not iv8:
            continue
        sizes, offsets = _parse_track_samples(data, handler)
        if not sizes:
            continue
        base_iv = int(iv8, 16)
        for idx, (co, s) in enumerate(zip(offsets, sizes)):
            iv = (base_iv + idx) << 64
            buf[co:co + s] = ctr_xor(bytes(buf[co:co + s]), key, iv)
    with open(out_path, "wb") as f:
        f.write(buf)


# ---------- ffmpeg 查找 ----------

def _maps_lines():
    try:
        with open("/proc/self/maps", "r", encoding="utf-8", errors="ignore") as f:
            return f.read().splitlines()
    except OSError:
        return []


def _so_paths(lines):
    paths = []
    for line in lines:
        parts = line.split()
        if parts and parts[-1].endswith(".so"):
            paths.append(parts[-1])
    return paths


def _android_native_lib_dir():
    lines = _maps_lines()
    paths = [p for p in _so_paths(lines) if p.startswith("/data/")]

    dirs = []
    apk_dirs = []
    for p in paths:
        if "!/lib/" in p:
            apk, _, abi = p.partition("!/lib/")
            abi = abi.split("/")[0]
            apk_dirs.append((os.path.dirname(apk), abi))
        else:
            dirs.append(os.path.dirname(p))

    for d in dict.fromkeys(dirs):
        if os.path.isfile(os.path.join(d, "libffmpeg.so")):
            return d

    for apk_dir, abi in apk_dirs:
        for name in (abi, abi.replace("-", ""), "arm64", "arm64-v8a"):
            d = os.path.join(apk_dir, "lib", name)
            if os.path.isfile(os.path.join(d, "libffmpeg.so")):
                return d

    for d in dict.fromkeys(dirs):
        try:
            if any(n.startswith(("libflutter", "libpython", "libserious")) for n in os.listdir(d)):
                return d
        except OSError:
            continue
    return None


def diagnose_engine() -> str:
    lines = _maps_lines()
    data_so = [p for p in _so_paths(lines) if p.startswith("/data/")]
    native = _android_native_lib_dir()
    found = find_ffmpeg()
    parts = [
        f"ffmpeg={found or 'None'}",
        f"nativeLib={native or 'None'}",
        f"mapsLines={len(lines)} dataSo={len(data_so)}",
    ]
    if native:
        parts.append(f"libffmpeg存在={os.path.isfile(os.path.join(native, 'libffmpeg.so'))}")
    if data_so:
        parts.append("sample=" + " | ".join(data_so[:3]))
    return "\n".join(parts)


def find_ffmpeg():
    env = (os.getenv("FFMPEG_PATH") or "").strip()
    if env and os.path.isfile(env):
        return env

    candidates = [os.path.join(data_dir(), "ffmpeg"), os.path.join(data_dir(), "bin", "ffmpeg")]
    native = _android_native_lib_dir()
    if native:
        candidates += [
            os.path.join(native, "libffmpeg.so"),
            os.path.join(native, "ffmpeg"),
        ]
    for path in candidates:
        if os.path.isfile(path):
            if not os.access(path, os.X_OK):
                try:
                    os.chmod(path, 0o755)
                except OSError:
                    continue
            return path
    return None


def _remux(dec_path, out_path, ffmpeg):
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", dec_path,
           "-c", "copy", "-tag:v", "hvc1", "-movflags", "+faststart", "-f", "mp4", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"ffmpeg 重封装失败：{result.stderr[:300]}")


def _decrypt_remux(enc_path, out_path, key_hex, ffmpeg):
    """ffmpeg 一步完成 CENC 解密 + hvc1 重封装（仅 bytevc1 轨可用）。"""
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-decryption_key", key_hex,
           "-i", enc_path, "-c", "copy", "-tag:v", "hvc1",
           "-movflags", "+faststart", "-f", "mp4", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"ffmpeg 解密重封装失败：{result.stderr[:300]}")


def _pick_track(tracks):
    """优先选择最小的 bytevc1（HEVC）轨；bytevc2 无法被 ffmpeg 转为 hvc1。"""
    if not tracks:
        return None

    def height(t):
        return int((t.get("video_meta") or {}).get("vheight", 0) or 0)

    hevc = [t for t in tracks if (t.get("video_meta") or {}).get("codec_type") == "bytevc1"]
    if hevc:
        return min(hevc, key=height)
    return max(tracks, key=height)


def _download(url, dest):
    with requests.get(url, stream=True, timeout=(10, 120)) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def local_video_path(vid, quality="worst") -> str:
    """返回可直接给播放器使用的本地 MP4 路径；首次调用会下载并解密。"""
    vid = str(vid or "").strip()
    if not vid:
        raise ValueError("vid 为空")

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg（手机端需打包 ffmpeg）")

    cache = os.path.join(data_dir(), "videos")
    os.makedirs(cache, exist_ok=True)
    out = os.path.join(cache, f"{vid}.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out

    track = _pick_track(resolve_tracks(vid))
    if not track or not track.get("main_url"):
        raise RuntimeError("无可用视频轨")
    codec = (track.get("video_meta") or {}).get("codec_type")
    key = unwrap_spade((track.get("encrypt_info") or {}).get("spade_a") or "")

    enc = out + ".enc"
    dec = out + ".dec"
    tmp = out + ".tmp"
    try:
        _download(track["main_url"], enc)
        try:
            _decrypt_remux(enc, tmp, key, ffmpeg)
        except RuntimeError:
            if codec != "bytevc1":
                raise RuntimeError("该清晰度使用 bytevc2 编码，手机端无法转换为 hvc1")
            decrypt_mp4(enc, key, dec)
            _remux(dec, tmp, ffmpeg)
        os.replace(tmp, out)
    finally:
        for p in (enc, dec, tmp):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
    return out
