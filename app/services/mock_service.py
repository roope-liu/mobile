"""框架测试用数据源：不依赖父项目的签名/coues，先把 UI 与播放链路跑通。"""

SAMPLE_DRAMAS = [
    {
        "series_id": "1001",
        "series_name": "框架测试剧 A",
        "episode_cnt": 3,
        "tags": ["测试"],
        "vid_list": ["demo-a-1", "demo-a-2", "demo-a-3"],
    },
    {
        "series_id": "1002",
        "series_name": "框架测试剧 B",
        "episode_cnt": 2,
        "tags": ["测试"],
        "vid_list": ["demo-b-1", "demo-b-2"],
    },
    {
        "series_id": "1003",
        "series_name": "播放器验证剧",
        "episode_cnt": 1,
        "tags": ["测试", "播放"],
        "vid_list": ["demo-c-1"],
    },
]


def search(keyword: str) -> list:
    kw = (keyword or "").strip()
    if not kw:
        return []
    return [d for d in SAMPLE_DRAMAS if kw in d["series_name"]]


def get_drama(series_id: str):
    for d in SAMPLE_DRAMAS:
        if d["series_id"] == str(series_id):
            return dict(d)
    return None
