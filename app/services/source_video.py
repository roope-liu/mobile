"""手机端视频解析：vid → 轨道列表 / spade 内容密钥（不依赖 Crypto/ffmpeg）。"""
import base64
import json
import sys
import time
import os

import requests

_COUES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "coues"))
if _COUES_PATH not in sys.path:
    sys.path.insert(0, _COUES_PATH)
from flurl.core import core_sixgod  # noqa: E402

VIDEO_API = "https://api5-normal-sinfonlineb.fqnovel.com/novel/player/multi_video_model/v1/"

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


def _fetch_video_model(vid):
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
    model = _fetch_video_model(vid)
    tracks = None
    if isinstance(model, dict):
        dv = model.get("dynamic_video")
        if isinstance(dv, dict):
            tracks = dv.get("dynamic_video_list")
        if not tracks:
            tracks = model.get("video_list")
    return tracks or []


def resolve_audio_tracks(vid) -> list:
    model = _fetch_video_model(vid)
    if not isinstance(model, dict):
        return []
    dv = model.get("dynamic_video")
    if isinstance(dv, dict):
        return dv.get("dynamic_audio_list") or []
    return []


def choose_track(tracks, quality="worst"):
    if not tracks:
        return None

    def height(t):
        return int((t.get("video_meta") or {}).get("vheight", 0) or 0)

    if quality in ("best", "worst"):
        return max(tracks, key=height) if quality == "best" else min(tracks, key=height)
    for t in tracks:
        if (t.get("video_meta") or {}).get("definition") == quality:
            return t
    return min(tracks, key=height)


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
