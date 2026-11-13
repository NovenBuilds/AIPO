"""已登记来源。同一平台只保留一条主路径，补充来源不把同一条材料算成第二份证据。"""

CAPABILITIES = {
    "search": "搜索",
    "body": "正文",
    "comments": "评论",
    "product": "商品",
    "import": "导入",
    "read": "补读",
    "hot": "热榜",
    "login_status": "登录状态",
}

# 平台别名 -> 规范名。规范名写入任务参数，避免 xhs 和「小红书」变成两个任务。
PLATFORM_ALIASES = {
    "小红书": ("小红书", "xhs", "xiaohongshu", "rednote"),
    "闲鱼": ("闲鱼", "咸鱼", "goofish", "xianyu"),
    "B站": ("B站", "b站", "bilibili", "哔哩哔哩"),
    "微博": ("微博", "weibo"),
    "知乎": ("知乎", "zhihu"),
    "抖音": ("抖音", "douyin"),
    "微信公众号": ("微信公众号", "公众号"),
    "百度": ("百度", "baidu"),
    "今日头条": ("今日头条", "头条", "toutiao"),
    "热榜": ("热榜",),
    "快手": ("快手", "kuaishou"),
    "贴吧": ("贴吧", "百度贴吧"),
    "Reddit": ("reddit",),
    "X": ("x.com", "twitter"),
    "YouTube": ("youtube",),
    "Hacker News": ("hacker news", "hackernews", "hn"),
    "Polymarket": ("polymarket",),
    "GitHub": ("github",),
    "V2EX": ("v2ex",),
    "网页": ("网页", "公开网页"),
}

SOURCES = [
    {
        "id": "xiaohongshu-mcp",
        "platforms": ["小红书"],
        "capabilities": ["login_status", "search", "body", "comments"],
        "role": "主路径",
        "site": "站内",
        "action": "只读 HTTP：/health、/api/v1/login/status、/api/v1/feeds/search、/api/v1/feeds/detail",
        "license": "Apache-2.0",
        "version_note": "历史验收写 v2.7.0；清单中的 go.mod 与 routes.go 指纹对齐远端 v2.6.0 与 v2.5.0，不对齐 v2.7.0。只读路径在 v2.7.0 仍存在。",
    },
    {
        "id": "goofish-cli",
        "platforms": ["闲鱼"],
        "capabilities": ["product"],
        "role": "主路径",
        "site": "站内",
        "action": "只读命令：auth status、search items、item get。不使用沙箱，不发消息、不发布。",
        "license": "Apache-2.0",
        "version_note": "清单三文件指纹与标签 v0.6.0（8124a6f17b5c）一致。回放使用标准化夹具，不是该版本的原生响应。",
    },
    {
        "id": "last30days-skill-cn",
        "platforms": ["B站", "微博", "知乎", "抖音", "微信公众号", "百度", "今日头条", "热榜"],
        "capabilities": ["search", "hot"],
        "role": "主路径",
        "site": "按渠道标注；百度、头条按公开索引",
        "action": "scripts/last30days.py --search cn --emit json。小红书不走这条，避免和本机服务重复计数。",
        "license": "MIT",
        "version_note": "提交 af785c682de2fb9192e495daf061308a7a6799ec，清单指纹一致。",
    },
    {
        "id": "last30days-skill",
        "platforms": ["Reddit", "X", "YouTube", "Hacker News", "Polymarket", "网页"],
        "capabilities": ["search"],
        "role": "主路径",
        "site": "按渠道标注",
        "action": "skills/last30days/scripts/last30days.py --emit json。--search 只用任务点名的来源；没有点名时沿用该项目已有配置，不写死 Reddit 和 Hacker News。不使用 --mock。",
        "license": "MIT",
        "version_note": "提交 f3cd06a620e385ce15109ed6d3b70fc20c89eccc，项目声明 3.30.0，清单指纹一致。",
    },
    {
        "id": "Agent-Reach",
        "platforms": ["GitHub", "V2EX", "网页"],
        "capabilities": ["read"],
        "role": "主路径",
        "site": "按返回渠道标注",
        "action": "agent-reach read <URL>。只补读给定链接。",
        "license": "MIT",
        "version_note": "提交 beabda7486e9a666360b18cdb5c0e759c2c4d20f，项目声明 1.6.0，清单指纹一致。",
    },
    {
        "id": "MediaCrawler",
        "platforms": ["小红书", "抖音", "快手", "B站", "微博", "贴吧", "知乎"],
        "capabilities": ["import", "comments"],
        "role": "补充导入",
        "site": "导入",
        "action": "只导入已有导出。不启动爬虫。许可证仅限非商业学习。",
        "license": "非商业学习许可证 1.1",
        "version_note": "pyproject.toml 与 cmd_arg/arg.py 指纹与远端提交 306ab4ca26c0e44fb87ede0e40e98748752815a6 一致，项目声明 0.1.0。不能据此认定整个压缩包相同。",
    },
    {
        "id": "social-media-copilot",
        "platforms": ["小红书", "抖音", "快手"],
        "capabilities": ["import"],
        "role": "补充导入",
        "site": "导入",
        "action": "只导入用户导出。不把源码存在当成插件已安装。",
        "license": "GPL-3.0",
        "version_note": "package.json 与 docs/xhs.md 指纹与远端提交 bcbb586aefcb0f5aad9821b40722712ddc36693c 一致，声明 0.1.10。",
    },
    {
        "id": "ai-goofish-monitor",
        "platforms": ["闲鱼"],
        "capabilities": ["import"],
        "role": "补充导入",
        "site": "导入",
        "action": "只导入已有 CSV 或 JSON。不启动监控、不登录账号。",
        "license": "MIT",
        "version_note": "pyproject.toml 与 src/api/routes/results.py 指纹与远端提交 77f8d75869acd65f9dba72731b95c7c49ea67bdf 一致。",
    },
    {
        "id": "host-web",
        "platforms": ["网页"],
        "capabilities": ["search"],
        "role": "补充",
        "site": "公开线索",
        "action": "实采时用已安装的 agent-reach 做公开网页搜索，并补读一条原文。没有命令时不编造结果。回放夹具仍标明公开线索。",
        "license": "宿主环境自有",
        "version_note": "不是八个上游之一。",
    },
]

PRIMARY = {
    "小红书": "xiaohongshu-mcp",
    "闲鱼": "goofish-cli",
    "B站": "last30days-skill-cn",
    "微博": "last30days-skill-cn",
    "知乎": "last30days-skill-cn",
    "抖音": "last30days-skill-cn",
    "微信公众号": "last30days-skill-cn",
    "百度": "last30days-skill-cn",
    "今日头条": "last30days-skill-cn",
    "热榜": "last30days-skill-cn",
    "快手": "social-media-copilot",
    "贴吧": "MediaCrawler",
    "Reddit": "last30days-skill",
    "X": "last30days-skill",
    "YouTube": "last30days-skill",
    "Hacker News": "last30days-skill",
    "Polymarket": "last30days-skill",
    "GitHub": "Agent-Reach",
    "V2EX": "Agent-Reach",
    "网页": "host-web",
}

SOURCE_BY_ID = {item["id"]: item for item in SOURCES}

IMPORT_SOURCES = ("MediaCrawler", "social-media-copilot", "ai-goofish-monitor")


def normalize_platform(value):
    raw = str(value or "").strip()
    lowered = raw.lower()
    for name, aliases in PLATFORM_ALIASES.items():
        if raw == name or lowered in aliases or raw in aliases:
            return name
    return raw


def normalize_platforms(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    found = []
    for value in values:
        name = normalize_platform(value)
        if name and name not in found:
            found.append(name)
    return found


def detect_platforms(question):
    text = question or ""
    lowered = text.lower()
    found = []
    for name, aliases in PLATFORM_ALIASES.items():
        if name in text or any(alias in lowered or alias in text for alias in aliases):
            if name not in found:
                found.append(name)
    return found


def render_matrix_md():
    lines = [
        "| 来源 | 平台 | 能力 | 角色 | 材料位置 | 本版动作 | 许可与版本核对 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in SOURCES:
        caps = "、".join(CAPABILITIES[name] for name in item["capabilities"])
        lines.append("| %s | %s | %s | %s | %s | %s | %s %s |" % (
            item["id"],
            "、".join(item["platforms"]),
            caps,
            item["role"],
            item["site"],
            item["action"],
            item["license"],
            item["version_note"],
        ))
    return "\n".join(lines) + "\n"
