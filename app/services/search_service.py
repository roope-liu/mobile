"""搜索服务：封装数据源调用，便于替换/测试。"""
from app.services.crawler import HongguoCrawler


_crawler = HongguoCrawler()


def search_dramas(keyword: str, crawler=None) -> list:
    """按名称搜索短剧，返回归一化结果列表。

    keyword 为空时直接返回空列表，不请求数据源。
    crawler 可注入（测试用），默认使用 HongguoCrawler。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    c = crawler if crawler is not None else _crawler
    return list(c.search(keyword) or [])
