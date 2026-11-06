"""手机端本地播放：下载 → 纯 Python AES-CTR 解密 → ffmpeg 重封装为 hvc1。"""
import os
import re
import ssl
import struct
import subprocess
import sys
import time
import zipfile

import requests

from app.services import cache_service
from app.services.aes_ctr import ctr_xor
from app.services.source_video import choose_track, resolve_audio_tracks, resolve_tracks, unwrap_spade
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


def _package_name():
    base = (os.getenv("FLET_APP_STORAGE_DATA") or "").replace("\\", "/")
    parts = [p for p in base.split("/") if p]
    if "user" in parts:
        i = parts.index("user")
        if i + 2 < len(parts):
            return parts[i + 2]
    if "data" in parts and len(parts) > 2:
        return parts[2]
    return None


def _device_abi():
    machine = (os.uname().machine or "").lower() if hasattr(os, "uname") else ""
    return {
        "aarch64": "arm64",
        "armv8l": "arm",
        "armv7l": "arm",
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "i686": "x86",
        "i386": "x86",
    }.get(machine, machine)


def _pm_apk_paths():
    pkg = _package_name()
    if not pkg:
        return []
    try:
        out = subprocess.run(
            ["/system/bin/pm", "path", pkg],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001
        return []
    return [line.split("package:", 1)[1].strip() for line in out.splitlines() if line.startswith("package:")]


def _native_lib_dirs():
    dirs = []
    abi = _device_abi()

    for apk in _pm_apk_paths():
        base = os.path.dirname(apk)
        for name in (abi, abi + "-v8a", "arm64-v8a", "armeabi-v7a", "arm64", "x86_64"):
            dirs.append(os.path.join(base, "lib", name))

    lines = _maps_lines()
    for p in _so_paths(lines):
        if not p.startswith("/data/"):
            continue
        if "!/lib/" in p:
            apk, _, tail = p.partition("!/lib/")
            abi_dir = tail.split("/")[0]
            dirs.append(os.path.join(os.path.dirname(apk), "lib", abi_dir))
        else:
            dirs.append(os.path.dirname(p))
    return list(dict.fromkeys(dirs))


def _abi_candidates():
    names = []
    native = _android_native_lib_dir()
    if native:
        installed = os.path.basename(native)
        names.append(installed)
        if installed == "arm64":
            names.append("arm64-v8a")
    machine = (os.uname().machine or "").lower() if hasattr(os, "uname") else ""
    if machine in ("aarch64", "armv8l", "armv7l"):
        names += ["arm64-v8a", "armeabi-v7a"]
    elif machine in ("x86_64", "amd64"):
        names += ["x86_64"]
    else:
        names += ["x86_64", "arm64-v8a", "armeabi-v7a"]
    abi = _device_abi()
    if abi and abi not in names:
        names.append(abi)
    return list(dict.fromkeys(names))


def _extract_ffmpeg_from_apks():
    """直接从 APK 内 lib/<abi>/libffmpeg.so 提取到应用数据目录。

    Flet/serious_python 打包时不会解压 native libs（AGP 默认 useLegacyPackaging=false），
    /data/app 下没有可执行文件。APK 本身可读，因此把目标 ABI 的二进制解出来再执行。
    """
    apk_paths = _pm_apk_paths()
    if not apk_paths:
        return None

    legacy = os.path.join(data_dir(), "bin", "ffmpeg")
    if os.path.isfile(legacy):
        try:
            os.remove(legacy)
        except OSError:
            pass

    for abi in _abi_candidates():
        target = os.path.join(data_dir(), "bin", f"ffmpeg-{abi}")
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return target

    for apk in apk_paths:
        try:
            with zipfile.ZipFile(apk) as zf:
                names = set(zf.namelist())
                for abi in _abi_candidates():
                    member = f"lib/{abi}/libffmpeg.so"
                    if member not in names:
                        continue
                    target = os.path.join(data_dir(), "bin", f"ffmpeg-{abi}")
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        while True:
                            chunk = src.read(1024 * 256)
                            if not chunk:
                                break
                            dst.write(chunk)
                    try:
                        os.chmod(target, 0o755)
                    except OSError:
                        pass
                    return target
        except (OSError, zipfile.BadZipFile):
            continue
    return None


def _android_native_lib_dir():
    for d in _native_lib_dirs():
        if os.path.isfile(os.path.join(d, "libffmpeg.so")):
            return d
    return None


def diagnose_engine() -> str:
    lines = _maps_lines()
    data_so = [p for p in _so_paths(lines) if p.startswith("/data/")]
    dirs = _native_lib_dirs()
    found = find_ffmpeg()
    parts = [
        f"ffmpeg={found or 'None'}",
        f"pkg={_package_name() or 'None'} abi={_device_abi() or 'None'}",
        f"nativeLib={_android_native_lib_dir() or 'None'}",
        f"mapsLines={len(lines)} dataSo={len(data_so)}",
    ]
    for d in dirs[:4]:
        exists = os.path.isfile(os.path.join(d, "libffmpeg.so"))
        parts.append(f"dir={d} libffmpeg存在={exists}")
    if found:
        try:
            probe = subprocess.run(
                [found, "-version"], capture_output=True, text=True,
                timeout=8, creationflags=_NO_WINDOW,
            )
            first = ((probe.stdout or probe.stderr or "").splitlines() or [""])[0][:80]
            parts.append(f"exec rc={probe.returncode} {first}")
        except Exception as exc:  # noqa: BLE001
            parts.append(f"exec失败：{str(exc)[:120]}")
    if data_so:
        parts.append("sample=" + " | ".join(data_so[:2]))
    return "\n".join(parts)


def find_ffmpeg():
    env = (os.getenv("FFMPEG_PATH") or "").strip()
    if env and os.path.isfile(env):
        return env

    candidates = []
    if _pm_apk_paths():
        extracted = _extract_ffmpeg_from_apks()
        if extracted:
            candidates.append(extracted)
    native = _android_native_lib_dir()
    if native:
        candidates += [
            os.path.join(native, "libffmpeg.so"),
            os.path.join(native, "ffmpeg"),
        ]
    candidates += [os.path.join(data_dir(), "ffmpeg"), os.path.join(data_dir(), "bin", "ffmpeg")]
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
           "-map", "0:v:0", "-an", "-c", "copy", "-tag:v", "hvc1",
           "-movflags", "+faststart", "-f", "mp4", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        detail = (result.stderr or "").strip()[:300] or f"rc={result.returncode}"
        raise RuntimeError(f"ffmpeg 重封装失败：{detail}")


def _decrypt_remux(enc_path, out_path, key_hex, ffmpeg):
    """ffmpeg 一步完成 CENC 解密 + hvc1 重封装（仅 bytevc1 轨可用）。"""
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-decryption_key", key_hex,
           "-i", enc_path, "-map", "0:v:0", "-an", "-c", "copy", "-tag:v", "hvc1",
           "-movflags", "+faststart", "-f", "mp4", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        detail = (result.stderr or "").strip()[:300] or f"rc={result.returncode}"
        raise RuntimeError(f"ffmpeg 解密重封装失败：{detail}")


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


class _TLSAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, ssl_context, **kwargs):
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().proxy_manager_for(*args, **kwargs)


def _download_once(url, dest, ssl_context=None):
    session = requests.Session()
    if ssl_context is not None:
        session.mount("https://", _TLSAdapter(ssl_context))
    try:
        with session.get(
            url,
            headers={
                "User-Agent": "com.phoenix.read/71332 (Linux; Android 16)",
                "Accept": "video/mp4,video/*,*/*;q=0.8",
                "Connection": "close",
            },
            stream=True,
            timeout=(20, 180),
        ) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
    finally:
        session.close()
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("下载内容为空")


def _tls12_context(verify=True):
    ctx = ssl.create_default_context()
    ctx.check_hostname = verify
    ctx.verify_mode = ssl.CERT_REQUIRED if verify else ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _download(url, dest):
    """下载带签名的 CDN 视频，兼容 Android 对部分 CDN TLS 连接的重置。"""
    attempts = (
        ("默认 TLS", None),
        ("TLS1.2", _tls12_context()),
        ("TLS1.2 不校验证书", _tls12_context(verify=False)),
    )
    last_error = None
    for label, ctx in attempts:
        try:
            _download_once(url, dest, ctx)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            try:
                if os.path.exists(dest):
                    os.remove(dest)
            except OSError:
                pass
            time.sleep(1.0)
    raise RuntimeError(f"视频下载失败（{label}）：{last_error}")


def _mux_files(ffmpeg, video_path, audio_path, out_path):
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", video_path]
    if audio_path:
        cmd += ["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a?"]
    cmd += ["-c", "copy", "-tag:v", "hvc1", "-movflags", "+faststart", "-f", "mp4", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        detail = (result.stderr or "").strip()[:300] or f"rc={result.returncode}"
        raise RuntimeError(f"ffmpeg 合并失败：{detail}")


def describe_streams(path, ffmpeg) -> str:
    """用 ffmpeg -i 读取流信息，确认成片是否带音轨。"""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", path],
            capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW,
        )
        text = result.stderr or ""
        has_video = "Video:" in text
        has_audio = "Audio:" in text
        return f"成片流：视频={'有' if has_video else '无'}，音频={'有' if has_audio else '无'}"
    except Exception as exc:  # noqa: BLE001
        return f"流信息读取失败：{str(exc)[:80]}"


def _decrypt_to(enc_path, key_hex, dec_path):
    if key_hex:
        decrypt_mp4(enc_path, key_hex, dec_path)
        return dec_path
    return enc_path


def local_video_path(vid, quality="worst", series_name="", episode=0) -> str:
    """返回可直接给播放器使用的本地 MP4 路径；首次调用会下载解密并合并音视频。"""
    vid = str(vid or "").strip()
    if not vid:
        raise ValueError("vid 为空")

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg（手机端需打包 ffmpeg）")

    cache = cache_service.videos_dir()
    out = cache_service.final_path(vid)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        cache_service.record(vid, series_name, episode)
        return out

    track = _pick_track(resolve_tracks(vid))
    if not track or not track.get("main_url"):
        raise RuntimeError("无可用视频轨")
    codec = (track.get("video_meta") or {}).get("codec_type")
    key = unwrap_spade((track.get("encrypt_info") or {}).get("spade_a") or "")

    audio_track = None
    for candidate in resolve_audio_tracks(vid) or []:
        if candidate.get("main_url"):
            audio_track = candidate
            break
    audio_key = ""
    if audio_track:
        audio_key = (audio_track.get("encrypt_info") or {}).get("spade_a") or ""

    enc = out + ".v.enc"
    dec = out + ".v.dec"
    aenc = out + ".a.enc"
    adec = out + ".a.dec"
    tmp = out + ".tmp"
    cleanup = (enc, dec, aenc, adec, tmp)
    try:
        _download(track["main_url"], enc)
        video_input = _decrypt_to(enc, key, dec)

        audio_input = None
        if audio_track:
            _download(audio_track["main_url"], aenc)
            audio_input = _decrypt_to(aenc, unwrap_spade(audio_key) if audio_key else "", adec)

        _mux_files(ffmpeg, video_input, audio_input, tmp)
        os.replace(tmp, out)
        cache_service.record(vid, series_name, episode)
    except RuntimeError:
        if codec != "bytevc1":
            raise RuntimeError("该清晰度使用 bytevc2 编码，手机端无法转换为 hvc1")
        raise
    finally:
        for p in cleanup:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
    return out
