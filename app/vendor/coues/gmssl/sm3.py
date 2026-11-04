import binascii
from math import ceil

from .func import rotl, bytes_to_list

IV = [
    1937774191, 1226093241, 388252375, 3666478592,
    2842636476, 372324522, 3817729613, 2969243214,
]

T_j = [2043430169] * 16 + [2055708042] * 48


def sm3_ff_j(x, y, z, j):
    if 0 <= j < 16:
        return x ^ y ^ z
    return (x & y) | (x & z) | (y & z)


def sm3_gg_j(x, y, z, j):
    if 0 <= j < 16:
        return x ^ y ^ z
    return (x & y) | ((~x) & z)


def sm3_p_0(x):
    return x ^ rotl(x, 9) ^ rotl(x, 17)


def sm3_p_1(x):
    return x ^ rotl(x, 15) ^ rotl(x, 23)


def sm3_cf(v_i, b_i):
    a, b, c, d, e, f, g, h = v_i
    w = [int.from_bytes(b_i[j:j + 4], "big") for j in range(0, 64, 4)]
    for j in range(16, 68):
        w.append(sm3_p_1(w[j - 16] ^ w[j - 9] ^ rotl(w[j - 3], 15)) ^ rotl(w[j - 13], 7) ^ w[j - 6])
    w1 = [w[j] ^ w[j + 4] for j in range(64)]
    for j in range(64):
        ss1 = rotl((rotl(a, 12) + e + rotl(T_j[j], j % 32)) & 0xffffffff, 7)
        ss2 = ss1 ^ rotl(a, 12)
        tt1 = (sm3_ff_j(a, b, c, j) + d + ss2 + w1[j]) & 0xffffffff
        tt2 = (sm3_gg_j(e, f, g, j) + h + ss1 + w[j]) & 0xffffffff
        d, c, b, a = c, rotl(b, 9), a, tt1
        h, g, f, e = g, rotl(f, 19), e, sm3_p_0(tt2)
    return [x ^ y for x, y in zip(v_i, [a, b, c, d, e, f, g, h])]


def sm3_hash(msg):
    msg = bytes(msg)
    bit_len = len(msg) * 8
    padded = msg + b"\x80"
    padded += b"\x00" * ((56 - len(padded) % 64) % 64)
    padded += bit_len.to_bytes(8, "big")
    v = IV[:]
    for offset in range(0, len(padded), 64):
        v = sm3_cf(v, padded[offset:offset + 64])
    return "".join(f"{x:08x}" for x in v)
