"""详情服务：封装数据源详情调用。"""
from app.services.crawler import HongguoCrawler


def get_drama(drama_id: str, crawler=None) -> dict | None:
    """获取短剧详情。drama_id 为空时直接返回 None，不请求数据源。"""
    drama_id = (drama_id or "").strip()
    if not drama_id:
        return None
    c = crawler if crawler is not None else HongguoCrawler()
    return c.get_drama(drama_id)
