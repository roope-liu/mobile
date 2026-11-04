"""视频解析与解密：vid → 下载密文 → AES-128-CTR 逐样本解密 → ffmpeg 剥离 CENC。

链路（逆向自 com.phoenix.read）：
1. POST multi_video_model/v1/ 拿 video_model.video_list
   - main_url：CDN 明文直链（下载加密 mp4）
   - encrypt_info.spade_a：包装的内容密钥（纯字节变换解出，无 KEK）
   - video_meta.definition：清晰度
2. spade_a 经 unwrap 得 content key（16B）
3. 读密文 senc 盒 base_iv，AES-128-CTR(key, IV=((base_iv+样本序号)<<64)) 逐样本解密
4. ffmpeg -c copy -tag:v hvc1 重封装剥离 CENC 信令 → 通用播放器可播

算法参考：github.com/zhangbaio/hongguo（红果短剧逆向，spade 为 libttmplayer.so 纯字节变换）
"""
import base64
import json
import os
import re
import struct
import subprocess
import sys
import time

import requests
from Crypto.Cipher import AES
from Crypto.Util import Counter as CTRCounter

_COUES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "vendor", "coues"))
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
if _COUES_PATH not in sys.path:
    sys.path.insert(0, _COUES_PATH)
from flurl.core import core_sixgod  # noqa: E402

VIDEO_API = "https://api5-normal-sinfonlineb.fqnovel.com/novel/player/multi_video_model/v1/"

# 视频版设备档案（Redmi 25053RT47C / 7.1.3.32），签名时使用
VIDEO_DEVICES = {
    "device_id": "4368802900374539",
    "iid": "4368802899821595",
    "install_id": "4368802899821595",
    "device_brand": "Redmi",
    "device_model": "25053RT47C",
    "device_type": "25053RT47C",
    "os_version": "16",
    "version_name": "7.1.3.32",
    "ua": "com.phoenix.read/71332 (Linux; U; Android 16; zh_CN; 25053RT47C; Build/BP1A.250305.015)",
}

SUPPORTED_CODECS = ("h264", "hevc", "av1", "vp9", "mpeg4", "hvc1", "hev1")


def _fetch_video_model(vid):
    """请求视频接口，返回 video_model dict（新版 dynamic_video / 旧版 video_list）。"""
    vid = str(vid)
    params = {
        "iid": "4368802899821595", "device_id": "4368802900374539", "ac": "wifi",
        "channel": "update_64", "aid": "8662", "app_name": "novelread",
        "version_code": "71332", "version_name": "7.1.3.32", "device_platform": "android",
        "os": "android", "ssmix": "a", "device_type": "25053RT47C", "device_brand": "Redmi",
        "language": "zh", "os_api": "36", "os_version": "16", "manifest_version_code": "71332",
        "resolution": "1280*2772", "dpi": "520", "update_version_code": "71332",
        "host_abi": "arm64-v8a", "dragon_device_type": "phone", "pv_player": "71332",
        "compliance_status": "0", "need_personal_recommend": "1", "player_so_load": "1",
        "is_android_pad_screen": "0",
    }
    body = {
        "biz_param": {
            "detail_page_version": 0, "device_level": 3, "disable_digg_stat": False,
            "disable_video_relate_book": False, "need_all_video_definition": True,
            "need_mp4_align": False, "use_os_player": False, "use_server_dns": False,
            "video_platform": 1024,
        },
        "mixed_video_id_map": {"1": [vid]},
    }
    headers = {
        "User-Agent": "com.phoenix.read/71332", "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8", "x-xs-from-web": "0",
        "sdk-version": "2", "x-ss-req-ticket": str(int(time.time() * 1000)),
        "passport-sdk-version": "50561", "x-vc-bdturing-sdk-version": "3.7.2.cn",
    }
    signed_headers, signed_url = core_sixgod(
        VIDEO_API, params, VIDEO_DEVICES, data=body, header=headers
    )
    resp = requests.post(
        signed_url, headers=signed_headers,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        timeout=(8, 20),
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"视频接口返回失败：{payload.get('code')}")
    data = (payload.get("data") or {}).get(vid) or {}
    video_model = data.get("video_model")
    if not video_model:
        raise RuntimeError(f"未找到 vid={vid} 的视频模型")
    if isinstance(video_model, str):
        video_model = json.loads(video_model)
    return video_model


def resolve_tracks(vid) -> list:
    """解析单集 vid，返回全部清晰度视频轨道列表。"""
    video_model = _fetch_video_model(vid)
    # 新版接口：dynamic_video.dynamic_video_list；旧版：video_list
    tracks = None
    if isinstance(video_model, dict):
        dv = video_model.get("dynamic_video")
        if isinstance(dv, dict):
            tracks = dv.get("dynamic_video_list")
        if not tracks:
            tracks = video_model.get("video_list")
    return tracks or []


def resolve_audio_tracks(vid) -> list:
    """解析单集 vid，返回音频轨道列表。"""
    video_model = _fetch_video_model(vid)
    if not isinstance(video_model, dict):
        return []
    dv = video_model.get("dynamic_video")
    if isinstance(dv, dict):
        return dv.get("dynamic_audio_list") or []
    return []


def choose_track(tracks, quality="best"):
    """从轨道列表选清晰度。quality: best/worst 或 '1080p'/'720p' 等。"""
    if not tracks:
        return None

    def height(t):
        return int((t.get("video_meta") or {}).get("vheight", 0) or 0)

    if quality in ("best", "worst"):
        return max(tracks, key=height) if quality == "best" else min(tracks, key=height)

    for t in tracks:
        if (t.get("video_meta") or {}).get("definition") == quality:
            return t
    target = int(quality.rstrip("p")) if quality.rstrip("p").isdigit() else None
    if target is None:
        return max(tracks, key=height)
    candidates = [t for t in tracks if height(t) <= target]
    return max(candidates, key=height) if candidates else min(tracks, key=height)


# ---------- spade_a → content key（libttmplayer.so FUN_001c4550 纯字节变换） ----------

def _popcount(x):
    return bin(x & 0xFFFFFFFF).count("1")


def _s8(v):
    v &= 0xFF
    return v - 256 if v >= 128 else v


def _strncmp0(a, b, n):
    for k in range(n):
        ca = a[k] if k < len(a) else 0
        cb = b[k] if k < len(b) else 0
        if ca != cb:
            return False
        if ca == 0:
            return True
    return True


def unwrap_spade(spade_a_b64) -> str:
    """spade_a(base64) → content key(32 hex)。ver1 纯字节变换，无 KEK/无 AES。"""
    spade = base64.b64decode(spade_a_b64)
    length = len(spade)
    if length < 3:
        raise RuntimeError("spade_a 长度非法")
    b_var5 = spade[0] ^ spade[1] ^ spade[2]
    type_len = b_var5 - 0x30
    if type_len < 1:
        raise RuntimeError("spade_a 类型长度非法")
    work_len = (length - b_var5) + 0x2F
    if work_len < 1 or 1 + work_len > length:
        raise RuntimeError("spade_a 工作区长度非法")
    dest = bytearray(spade[1:1 + work_len])

    # 解出 type 字符串，判断 v1 / v2
    s1 = bytearray(type_len)
    b16 = spade[length - type_len - 2]
    b14 = spade[length - type_len - 1]
    for i in range(type_len):
        s1[i] = b14 ^ b16 ^ spade[i + (length - type_len)]
    if _strncmp0(s1, b"app_v2", type_len) or _strncmp0(s1, b"web_v2", type_len):
        raise RuntimeError("spade_a 为 ver2，暂不支持")

    b14, b16 = 0x55, 0xFA
    for i in range(work_len):
        b6 = dest[i]
        u18 = _popcount(i)
        b3, b7 = b6, b14
        if i & 1:
            b3, b7, b16 = b16, b6, b14
        c_var4 = _s8(-0x15 - u18)
        dest[i] = (c_var4 + (b16 ^ b6)) & 0xFF
        b14, b16 = b7, b3

    b0 = dest[0]
    if 0x30 <= b0 <= 0x39:
        u11 = b0 - 0x30
    elif 0x61 <= b0 <= 0x7A:
        u11 = b0 - 0x57
    else:
        raise RuntimeError("spade_a 解出非 hex 头部")
    cut = work_len - (u11 & 0xFF)
    if cut < 2:
        raise RuntimeError("spade_a 解出密钥过短")
    return bytes(dest[1:cut]).decode("latin1", "replace")


# ---------- MP4 CENC AES-128-CTR 解密 ----------

def _ib(data, start, end):
    """MP4 box 迭代器：产出 (type, offset, size, header_size)。"""
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
    """解析指定轨(vide/soun)样本 → (sizes, offsets)。"""
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
    """解密 mp4 全部加密轨（视频+音频）。"""
    data = open(enc_path, "rb").read()
    buf = bytearray(data)
    key = bytes.fromhex(key_hex)
    moov = _find(data, [b"moov"])
    if not moov:
        raise RuntimeError("密文无 moov 盒")
    stats = {}
    for box_type, o, size, header_size in _ib(data, *moov):
        if box_type != b"trak":
            continue
        h = _find(data, [b"mdia", b"hdlr"], o + header_size, o + size)
        handler = data[h[0] + 8:h[0] + 12] if h else None
        if handler not in (b"vide", b"soun"):
            continue
        iv8 = _trak_senc_iv8(data, o, o + size)
        if not iv8:
            continue  # 该轨未加密
        sizes, offsets = _parse_track_samples(data, handler)
        if not sizes:
            continue
        base_iv = int(iv8, 16)
        for idx, (co, s) in enumerate(zip(offsets, sizes)):
            iv = (base_iv + idx) << 64
            counter = CTRCounter.new(128, initial_value=iv)
            buf[co:co + s] = AES.new(key, AES.MODE_CTR, counter=counter).decrypt(bytes(buf[co:co + s]))
        if handler == b"vide":
            ok = sum(1 for co, s in zip(offsets, sizes) if _nal_ok(bytes(buf[co:co + s]), s))
            stats["vide"] = (ok, len(sizes))
        else:
            stats["soun"] = (None, len(sizes))
    with open(out_path, "wb") as f:
        f.write(buf)
    return stats


def _nal_ok(pt, size):
    p = 0
    while p + 4 <= size:
        length = struct.unpack(">I", pt[p:p + 4])[0]
        if length == 0 or p + 4 + length > size:
            return False
        p += 4 + length
    return p == size


def remux_mp4(dec_path, out_path, ffmpeg_path):
    """ffmpeg 重封装剥离 CENC 信令（encv→hvc1），使严格播放器可播。"""
    cmd = [ffmpeg_path, "-y", "-loglevel", "error", "-i", dec_path,
           "-c", "copy", "-tag:v", "hvc1", "-movflags", "+faststart", "-f", "mp4", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"ffmpeg 重封装失败：{result.stderr[:200]}")
    return out_path
