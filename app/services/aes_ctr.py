"""纯 Python AES-128-CTR（T-table 优化，用于手机端解密，避免 Android 打包 C 扩展）。"""


def _gmul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _pow(a: int, n: int) -> int:
    r = 1
    while n:
        if n & 1:
            r = _gmul(r, a)
        a = _gmul(a, a)
        n >>= 1
    return r


def _rotl8(x: int, n: int) -> int:
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _rotr32(w: int, n: int) -> int:
    return ((w >> n) | (w << (32 - n))) & 0xFFFFFFFF


def _build_tables():
    sbox = [0] * 256
    for x in range(256):
        inv = 0 if x == 0 else _pow(x, 254)
        sbox[x] = inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2) ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63
    te0, te1, te2, te3 = [], [], [], []
    for x in range(256):
        s = sbox[x]
        w = (_gmul(s, 2) << 24) | (s << 16) | (s << 8) | _gmul(s, 3)
        te0.append(w)
        te1.append(_rotr32(w, 8))
        te2.append(_rotr32(w, 16))
        te3.append(_rotr32(w, 24))
    return sbox, te0, te1, te2, te3


_SBOX, _TE0, _TE1, _TE2, _TE3 = _build_tables()
_RCON = [0x01]
for _ in range(9):
    _RCON.append(_gmul(_RCON[-1], 2))


def _expand_key(key: bytes):
    w = [int.from_bytes(key[i:i + 4], "big") for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = ((_SBOX[(t >> 24) & 0xFF] << 24) | (_SBOX[(t >> 16) & 0xFF] << 16)
                 | (_SBOX[(t >> 8) & 0xFF] << 8) | _SBOX[t & 0xFF])
            t ^= _RCON[i // 4 - 1] << 24
        w.append(w[i - 4] ^ t)
    return w


def _encrypt_block(block: bytes, rk) -> bytes:
    s0 = int.from_bytes(block[0:4], "big") ^ rk[0]
    s1 = int.from_bytes(block[4:8], "big") ^ rk[1]
    s2 = int.from_bytes(block[8:12], "big") ^ rk[2]
    s3 = int.from_bytes(block[12:16], "big") ^ rk[3]
    k = 4
    for _ in range(9):
        t0 = _TE0[s0 >> 24] ^ _TE1[(s1 >> 16) & 255] ^ _TE2[(s2 >> 8) & 255] ^ _TE3[s3 & 255] ^ rk[k]
        t1 = _TE0[s1 >> 24] ^ _TE1[(s2 >> 16) & 255] ^ _TE2[(s3 >> 8) & 255] ^ _TE3[s0 & 255] ^ rk[k + 1]
        t2 = _TE0[s2 >> 24] ^ _TE1[(s3 >> 16) & 255] ^ _TE2[(s0 >> 8) & 255] ^ _TE3[s1 & 255] ^ rk[k + 2]
        t3 = _TE0[s3 >> 24] ^ _TE1[(s0 >> 16) & 255] ^ _TE2[(s1 >> 8) & 255] ^ _TE3[s2 & 255] ^ rk[k + 3]
        s0, s1, s2, s3 = t0, t1, t2, t3
        k += 4

    def final(a, b, c, d):
        return ((_SBOX[a >> 24] << 24) | (_SBOX[(b >> 16) & 255] << 16)
                | (_SBOX[(c >> 8) & 255] << 8) | _SBOX[d & 255])

    o0 = final(s0, s1, s2, s3) ^ rk[k]
    o1 = final(s1, s2, s3, s0) ^ rk[k + 1]
    o2 = final(s2, s3, s0, s1) ^ rk[k + 2]
    o3 = final(s3, s0, s1, s2) ^ rk[k + 3]
    return (o0.to_bytes(4, "big") + o1.to_bytes(4, "big")
            + o2.to_bytes(4, "big") + o3.to_bytes(4, "big"))


def ctr_xor(data: bytes, key: bytes, initial_counter: int) -> bytes:
    """AES-128-CTR：计数器为 128 位大端整数，逐块 +1。"""
    rk = _expand_key(key)
    out = bytearray(data)
    counter = initial_counter
    for off in range(0, len(data), 16):
        stream = _encrypt_block(counter.to_bytes(16, "big"), rk)
        end = min(off + 16, len(data))
        for i in range(end - off):
            out[off + i] ^= stream[i]
        counter = (counter + 1) & ((1 << 128) - 1)
    return bytes(out)
