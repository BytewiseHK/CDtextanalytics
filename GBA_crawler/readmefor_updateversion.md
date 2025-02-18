#How to run:
User Interaction:
Keywords: When prompted, enter keywords related to the news you're interested in. Example:
Enter keywords (comma-separated, use Chinese characters, example: 政策, 规划, 建设, 交通, 发展, 会议, 项目): 
If you don't enter any, default keywords will be used. 
Days Range: Input how many days back you want to check for articles:
Enter the number of days for article publication range (1-7): 
Cities Selection: Specify which cities you want to monitor from the list provided:
Enter cities to search (comma-separated, available options: Guangzhou, Shenzhen, Zhuhai, Dongguan, Zhongshan, Jiangmen, Zhaoqing, Huizhou, South China Net, Hong Kong, Macau):
Start Crawling: Press Enter to start the crawling process.
Interactive Commands:
stop: Stops the crawler.
status: Shows current status like processed pages and found articles.
articles: Lists or shows some found articles.
future: Displays articles with future events.
search: Searches through found articles for keywords.
keywords: Adds new keywords to the search criteria.
days: Changes the days range for article publication.
cities: Allows reselection of cities to monitor.
Monitor Progress: You'll see real-time updates on how many pages have been processed and articles found.

Output
Articles: Saved as JSON files in the specified output directory.
Log: Crawling operations are logged in crawl_log.jsonl.
Report: An HTML report summarizing the findings will be generated at the end in the output directory named report.html.

And you can stop the process by pressing Ctrl + C to end it earlierly.


# 🌉 粤港澳大湾区新闻监测系统

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

智能监测大湾区各城市新闻动态，自动识别未来重要事件并生成可视化报告。

## 🚀 功能特性

- 多源新闻采集（支持广州日报、深圳新闻网等主流媒体）
- 智能内容识别（政策/基建/经济相关报道）
- 未来事件检测（自动识别新闻中的未来时间节点）
- 动态去重机制（基于Simhash的内容指纹技术）
- 自动生成HTML简报（支持时间线可视化）

## ⚙️ 系统配置

```python
CONFIG = {
    "sources": {
        "广州": "https://news.dayoo.com/guangzhou/",
        "深圳": "https://www.sznews.com/news/",
        "珠海": "https://news.hizh.cn/",
        '东莞': 'https://news.sun0769.com/dg/headnews/',
        '中山': 'https://www.zsnews.cn/news/',
        '江门': 'http://www.jmnews.com.cn/',
        '肇庆': 'http://www.xjrb.com/',
        '惠州': 'http://www.huizhou.cn/',
        '南方网': 'https://news.southcn.com/',
        '深圳会展中心': 'https://www.szcec.com/Schedule/index.html%23yue9%EF%BC%8C',
        '香港旅游局': 'https://www.discoverhongkong.com/hk-tc/what-s-new/events.html',
        '香港贸发局': 'https://event.hktdc.com/tc/',
        '政府统计处': 'https://www.censtatd.gov.hk/sc/',
        '政府新闻网': 'https://www.info.gov.hk/gia/general/ctoday.htm',
        '香港旅游网': 'https://partnernet.hktb.com/en/trade_support/trade_events/conventions_exhibitions/index.html?displayMode=&viewMode=calendar&isSearch=true&keyword=&area=0&location=&from=&to=&searchMonth=--+Please+Select+--&ddlDisplayMode_selectOneMenu=All',
        '澳门旅游局': 'https://www.macaotourism.gov.mo/zh-hant/events/'
    },
    "keywords": ["政策", "峰会", "基建"],
    "output_dir": "reports",
    "schedule": "daily 08:00"
}


├── crawlers/            # 爬虫模块
├── analysis/            # 内容分析模块
├── utils/               # 工具函数
├── config.py            # 配置文件
├── main.py              # 主程序
└── scheduler.py         # 定时任务



# GBANewsMonitor

A Python script designed to monitor and collect news articles from specified Chinese cities with an emphasis on future-oriented content. This crawler uses asynchronous programming for efficient web scraping, filtering articles based on user-defined keywords and publication dates.

## Features

### User Interaction
- **Keyword Selection**: Users can input keywords in Chinese to filter articles. Default keywords include topics like policy, planning, construction, traffic, development, meetings, and projects.
- **Date Range**: Users define how many days back the articles should be searched from the current date.
- **City Selection**: Users can select one or multiple cities from a predefined list to focus the crawl.

### Crawling Capabilities
- **Asynchronous Crawling**: Utilizes `aiohttp` for non-blocking HTTP requests, enabling concurrent processing of web pages.
- **Depth Control**: Limits how deep into the website structure the crawler goes (`max_depth`).
- **Page Limit**: Stops after processing a maximum number of pages (`max_pages`).
- **Timeout Control**: Sets a timeout for each request to avoid hanging on slow or unresponsive sites.
- **Concurrency Limit**: Controls how many pages can be processed at the same time for better resource management.

### Data Processing
- **Content Filtering**: Articles are processed to check if they contain future dates or match user-specified keywords.
- **Deduplication**: Uses Simhash for content fingerprinting to avoid saving duplicate articles.
- **Date Detection**: Employs `dateparser` to parse various date formats mentioned in articles, focusing on future events or plans.

### Storage and Reporting
- **Article Saving**: Saves articles in JSON format, including metadata like URL and publication date.
- **Logging**: All operations are logged in JSON lines format for traceability.
- **Reports Generation**: 
  - A text report summarizing the crawl statistics.
  - An HTML report detailing articles with future content, including sentences that mention future dates.

### User Commands During Execution
- **Stop**: Manually stop the crawler.
- **Status**: Check current crawl statistics.
- **Articles**: Display a list of found articles.
- **Future**: Show articles containing future dates.
- **Search**: Search within found articles using keywords.
- **Keywords**: Add or change search keywords dynamically.
- **Days**: Adjust the publication date range on-the-fly.
- **Cities**: Change the selection of cities to crawl.

## Requirements
- Python 3.7+
- `aiohttp` for asynchronous HTTP requests
- `BeautifulSoup` for HTML parsing
- `dateparser` for parsing dates in various formats
- `jieba` for Chinese text segmentation
- `simhash` for content deduplication
- `json` for JSON operations
- `logging` for logging operations

