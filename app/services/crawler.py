"""数据源服务：红豆短剧 (https://hongguoduanju.com/)。

- 搜索走番茄系 app 接口（需 X-Gorgon 等签名，签名由 coues/flurl 提供）
- 详情走网站 SSR 页面，数据内嵌在 HTML 的 `_ROUTER_DATA = {...}` 里
"""
import json
import os
import re
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

# 签名库 coues/flurl 以「flurl」为顶层包名，需把 coues 目录加入 sys.path
_COUES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "coues"))
if _COUES_PATH not in sys.path:
    sys.path.insert(0, _COUES_PATH)
from flurl.core import core_sixgod  # noqa: E402

SITE = "https://hongguoduanju.com"
SEARCH_URL = "https://api5-normal-sinfonlinec.fqnovel.com/reading/bookapi/search/tab/v"
WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
DEVICE_ID = "4368802900374539"
INSTALL_ID = "4368802899821595"

# 搜索结果缓存：{keyword: (results, expire_ts)}，避免同一关键词重复多次翻页抓取
_SEARCH_CACHE = {}
_SEARCH_CACHE_TTL = 300      # 5 分钟内重复搜索直接命中缓存
_SEARCH_CACHE_MAX = 128
_SEARCH_LOCK = threading.Lock()

# 复用连接，减少每次请求的 TCP/TLS 握手开销
_session = requests.Session()
_session.mount(
    "https://",
    requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=32, max_retries=1),
)


class _TLS12Adapter(requests.adapters.HTTPAdapter):
    def __init__(self, ssl_context, **kwargs):
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().proxy_manager_for(*args, **kwargs)


_tls12_session = None


def _get_tls12_session():
    global _tls12_session
    if _tls12_session is None:
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        sess = requests.Session()
        sess.mount("https://", _TLS12Adapter(ctx, max_retries=1))
        _tls12_session = sess
    return _tls12_session


def _http_get(url, headers, timeout=(8, 20)):
    """带重试与 TLS1.2 回退的 GET，兼容部分 Android 设备对 TLS 的重置。"""
    last_error = None
    for session in (_session, _get_tls12_session(), _session):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.6)
    raise last_error


def _cache_get(key):
    now = time.time()
    hit = _SEARCH_CACHE.get(key)
    if hit and hit[1] > now:
        return hit[0]
    if hit:
        _SEARCH_CACHE.pop(key, None)
    return None


def _cache_set(key, value):
    with _SEARCH_LOCK:
        _SEARCH_CACHE[key] = (value, time.time() + _SEARCH_CACHE_TTL)
        while len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))

# 搜索版设备档案（XIAOMI 2509FPN0BC / 7.1.5.32），签名时使用
SEARCH_DEVICES = {
    "device_id": DEVICE_ID,
    "iid": INSTALL_ID,
    "install_id": INSTALL_ID,
    "device_brand": "XIAOMI",
    "device_model": "2509FPN0BC",
    "device_type": "2509FPN0BC",
    "os_version": "9",
    "version_name": "7.1.5.32",
    "ua": "com.phoenix.read/71532 (Linux; U; Android 9; zh_CN; 2509FPN0BC; Build/PQ3A.190605.07291804)",
}


def _cn_to_int(text: str) -> int:
    """把「一 / 十 / 十一 / 二十三 / 12」等季序号转为整数，失败返回 0。"""
    text = str(text or "").strip()
    if text.isdigit():
        return int(text)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100}
    total = 0
    current = 0
    for ch in text:
        if ch in digits:
            current = digits[ch]
        elif ch in units:
            total += (current or 1) * units[ch]
            current = 0
        else:
            return 0
    return total + current


def normalize_series(raw: dict) -> dict:
    """把搜索结果 / 详情里的剧目原始字段归一化为统一结构。

    统一输出 series_id / series_name / tags / episode_cnt，其余原始字段
    （封面、简介等）原样保留，供前端按需使用。
    """
    out = dict(raw or {})
    out["series_id"] = str(out.get("series_id", ""))
    out["series_name"] = (
        out.get("series_title")
        or out.get("series_name")
        or out.get("title")
        or "未命名短剧"
    )
    tags = out.get("tags")
    if not tags:
        category_list = out.get("category_list") or []
        tags = [c.get("name") for c in category_list if c.get("name")]
    out["tags"] = tags or []
    vid_list = [str(v) for v in (out.get("vid_list") or []) if v]
    if out.get("episode_cnt") is None:
        out["episode_cnt"] = len(vid_list)
    out["vid_list"] = vid_list
    return out


class HongguoCrawler:
    """红豆短剧数据抓取器。"""

    def _search_once(self, keyword: str, passback: str = "", count: int = 20) -> dict:
        """单次调用搜索接口，返回原始 payload。"""
        params = {
            "query": keyword,
            "tab_type": "11",
            "tab_name": "feed",
            "offset": "0",
            "count": str(count) if not passback else "0",
            "bookstore_tab": "16",
            "search_source": "1",
            "only_feed": "false",
            "use_correct": "true",
            "aid": "8662",
            "device_platform": "android",
            "version_code": "71532",
            "version_name": "7.1.5.32",
            "iid": INSTALL_ID,
            "device_id": DEVICE_ID,
            "ac": "wifi",
            "channel": "oppo_8662_64",
            "app_name": "novelread",
            "device_type": "2509FPN0BC",
            "device_brand": "XIAOMI",
            "os_api": "28",
            "os_version": "9",
            "language": "zh",
            "ssmix": "a",
            "manifest_version_code": "71532",
            "update_version_code": "71532",
            "user_is_login": "0",
        }
        if passback:
            params["passback"] = passback

        headers = {"User-Agent": SEARCH_DEVICES["ua"], "Accept": "application/json"}
        signed_headers, signed_url = core_sixgod(
            SEARCH_URL, params, SEARCH_DEVICES, data={}, header=headers
        )
        resp = _http_get(signed_url, headers=signed_headers, timeout=(8, 20))
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"搜索接口返回失败：{payload.get('code')}")
        return payload

    @staticmethod
    def _extract_series(node, out: list, seen: set) -> None:
        """递归收集节点内所有含 series_id 的剧目（用于系列剧/其他版本嵌套卡片）。

        字符串若为 JSON（如 lynx_data），会尝试解析后继续递归。
        """
        if isinstance(node, str):
            text = node.strip()
            if text[:1] in ("{", "["):
                try:
                    node = json.loads(text)
                except json.JSONDecodeError:
                    return
            else:
                return
        if isinstance(node, dict):
            if node.get("series_id") and (
                node.get("series_title") or node.get("title") or node.get("series_name")
            ):
                item = normalize_series(node)
                if item["series_id"] and item["series_id"] not in seen:
                    seen.add(item["series_id"])
                    out.append(item)
            for value in node.values():
                HongguoCrawler._extract_series(value, out, seen)
        elif isinstance(node, list):
            for value in node:
                HongguoCrawler._extract_series(value, out, seen)

    def _collect_from_cell(self, cell: dict, out: list, seen: set) -> None:
        """从单个搜索卡片提取剧目：直接 video_data / video_detail，以及嵌套的系列剧卡片。"""
        item = None
        video_detail = cell.get("video_detail")
        if isinstance(video_detail, dict) and video_detail.get("series_id"):
            item = normalize_series(video_detail)
        else:
            video_data = cell.get("video_data")
            if isinstance(video_data, str):
                try:
                    video_data = json.loads(video_data)
                except json.JSONDecodeError:
                    video_data = None
            if isinstance(video_data, list):
                for it in video_data:
                    if isinstance(it, dict) and it.get("series_id"):
                        it = dict(it)
                        it.setdefault("series_name", it.get("title"))
                        it.setdefault("series_cover", it.get("cover"))
                        item = normalize_series(it)
                        break
        if item and item["series_id"] and item["series_id"] not in seen:
            seen.add(item["series_id"])
            out.append(item)

        # 系列剧 / 其他版本 / 社区帖等卡片：数据深嵌在 lynx_data、post_data 等字段里，
        # 递归整卡提取所有含 series_id 的剧目（后续再按相关性排序过滤）。
        self._extract_series(cell, out, seen)

    @staticmethod
    def _norm_name(text: str) -> str:
        """归一化名称用于相关性匹配：去空白与常见标点。"""
        return re.sub(r"[\s：:·《》【】\[\]()（）,，.。!！?？\-—_]+", "", str(text or "")).lower()

    def search(self, keyword: str, passback: str = "", count: int = 20,
               max_pages: int = 2, page_size: int = 20,
               enough_hits: int = 6) -> list:
        """按名称搜索短剧，自动翻页并按 series_id 去重。

        - 单页内既解析常规结果，也解析「系列剧 / 其他版本」等嵌套卡片
        - 通过 has_more + passback 翻页，默认最多 2 页（速度优先）
        - 命中足够的相关结果（enough_hits）后提前停止，避免无谓翻页
        - 相同关键词在 TTL 内直接命中缓存
        - 按名称相关性过滤并排序（名称含关键词者优先，无关推荐项剔除）
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return []

        cache_key = (keyword, int(page_size))
        if not passback:
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached

        key = self._norm_name(keyword)
        results = []
        seen = set()
        pb = passback
        pages = max_pages if not passback else 1
        for _ in range(pages):
            payload = self._search_once(keyword, passback=pb, count=page_size)
            tabs = payload.get("search_tabs") or []
            # 优先「综合」tab（tab_type 11），没有则遍历全部
            feed_tab = next((t for t in tabs if t.get("tab_type") == 11), None)
            scan_tabs = [feed_tab] if feed_tab else tabs
            before = len(results)
            for tab in scan_tabs:
                for cell in tab.get("data") or []:
                    self._collect_from_cell(cell, results, seen)

            # 提前停止：已命中足够相关结果；或本页无新增（后续大概率重复）
            matched = sum(1 for it in results
                          if key and key in self._norm_name(it.get("series_name")))
            if (matched >= enough_hits and len(results) >= enough_hits) \
                    or len(results) == before:
                break
            if not feed_tab or not feed_tab.get("has_more"):
                break
            pb = str(feed_tab.get("passback") or "")
            if not pb:
                break

        self._enrich_duplicate_names(results, keyword)
        ranked = self._rank_by_relevance(results, keyword)
        if not passback:
            _cache_set(cache_key, ranked)
        return ranked

    def _rank_by_relevance(self, results: list, keyword: str) -> list:
        """按名称与关键词的相关性排序；剔除无关推荐项（无匹配时保留全部）。

        排序规则：完全同名 > 名称含关键词 > 关键词被包含；
        同一基础名下按「季」序号升序（第一季、第二季…），再按集数降序。
        """
        key = self._norm_name(keyword)
        if not key:
            return results

        def base_name(name: str) -> str:
            # 去掉「：第N季 / 第N季 / 数字季」后缀，得到基础名用于分组
            return re.sub(r"第[0-9一二三四五六七八九十百零两]+季$", "", name)

        def season_no(name: str) -> int:
            m = re.search(r"第([0-9一二三四五六七八九十百零两]+)季", name)
            if not m:
                return 0
            return _cn_to_int(m.group(1))

        def score(item):
            name = self._norm_name(item.get("series_name"))
            if name == key:
                rank = 0
            elif key in name:
                rank = 1
            elif name and name in key:
                rank = 2
            else:
                rank = 3
            base = base_name(name)
            return (rank, base, season_no(name), -int(item.get("episode_cnt") or 0))

        scored = [(score(it), it) for it in results]
        matched = [it for s, it in scored if s[0] < 3]
        # 无任何相关结果时退回全部，避免搜不到
        pool = matched if matched else results
        return sorted(pool, key=score)

    def _enrich_duplicate_names(self, results: list, keyword: str, limit: int = 12) -> None:
        """搜索接口对部分分季剧只返回基础名（如「持械入宋」），

        对名称与关键词完全一致的多条结果并发抓详情补全季名，便于区分。
        失败静默忽略，不阻塞搜索。
        """
        key = self._norm_name(keyword)
        dupes = [it for it in results
                 if self._norm_name(it.get("series_name")) == key][:limit]
        if len(dupes) <= 1:
            return

        def enrich(item):
            try:
                drama = self.get_drama(item["series_id"])
            except Exception:  # noqa: BLE001 - 补全失败不影响搜索
                return
            if not drama:
                return
            name = drama.get("series_name")
            if name and self._norm_name(name) != key:
                item["series_name"] = name
            if drama.get("episode_cnt"):
                item["episode_cnt"] = drama["episode_cnt"]
            if drama.get("series_cover") and not item.get("series_cover"):
                item["series_cover"] = drama["series_cover"]

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(enrich, dupes))

    def get_drama(self, drama_id: str) -> dict | None:
        """获取短剧详情与剧集列表（含播放 vid 列表与社交信息）。"""
        drama_id = (drama_id or "").strip()
        if not re.fullmatch(r"\d{10,24}", drama_id):
            return None

        url = f"{SITE}/detail?series_id={drama_id}"
        resp = _http_get(url, headers={"User-Agent": WEB_UA}, timeout=(8, 20))
        resp.raise_for_status()

        match = re.search(r"window\._ROUTER_DATA\s*=\s*|_ROUTER_DATA\s*=\s*", resp.text)
        if not match:
            raise RuntimeError("页面结构已变化：未找到 _ROUTER_DATA")

        data, _ = json.JSONDecoder().raw_decode(resp.text[match.end():].lstrip())
        loader = data.get("loaderData", {}) if isinstance(data, dict) else {}

        page = self._find_with_series_detail(loader)
        if not page:
            return None

        series_detail = page.get("seriesDetail") or {}
        drama = normalize_series(series_detail)
        drama["social"] = page.get("seriesSocialInfo") or {}
        return drama

    @staticmethod
    def _find_with_series_detail(node):
        """在 loaderData 里递归找第一个含 seriesDetail 字段的对象。"""
        if isinstance(node, dict):
            if "seriesDetail" in node:
                return node
            for value in node.values():
                found = HongguoCrawler._find_with_series_detail(value)
                if found:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = HongguoCrawler._find_with_series_detail(value)
                if found:
                    return found
        return None
