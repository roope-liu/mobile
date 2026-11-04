import os

import pytest

from app.services.aes_ctr import ctr_xor
from app.services.ondevice import _pick_track


def test_aes_ctr_matches_reference():
    pytest.importorskip("Crypto")
    from Crypto.Cipher import AES
    from Crypto.Util import Counter

    key = os.urandom(16)
    data = os.urandom(4096 + 7)
    iv = (123456789 << 64)
    ours = ctr_xor(data, key, iv)
    ref = AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=iv)).decrypt(data)
    assert ours == ref


def test_pick_track_prefers_bytevc1():
    tracks = [
        {"video_meta": {"codec_type": "bytevc2", "vheight": 720}, "main_url": "a"},
        {"video_meta": {"codec_type": "bytevc1", "vheight": 1080}, "main_url": "b"},
        {"video_meta": {"codec_type": "bytevc1", "vheight": 1080}, "main_url": "c"},
    ]
    picked = _pick_track(tracks)
    assert picked["main_url"] == "b"
    assert _pick_track([]) is None
