import aiohttp
import re
import json
import os
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from simhash import Simhash
import dateparser
import jieba
import asyncio
import logging
from jieba import posseg
from typing import List, Dict, Set
import itertools
from jinja2 import Template

# Configuration parameters
CONFIG = {
    "entry_points": {
        "Guangzhou": [
            {"label": "Main News", "url": "https://news.dayoo.com/guangzhou/"},
        ],
        "Shenzhen": [
            {"label": "Main News", "url": "https://www.sznews.com/news/"},
            {"label": "Exhibition Center", "url": "https://www.szcec.com/Schedule/index.html%23yue9%EF%BC%8C"}
        ],
        "Zhuhai": [
            {"label": "Main News", "url": "https://news.hizh.cn/"}
        ],
        'Dongguan': [
            {"label": "Head News", "url": 'https://news.sun0769.com/dg/headnews/'}
        ],
        'Zhongshan': [
            {"label": "News", "url": 'https://www.zsnews.cn/news/'}
        ],
        'Jiangmen': [
            {"label": "Local News", "url": 'http://www.jmnews.com.cn/'}
        ],
        'Zhaoqing': [
            {"label": "Local Paper", "url": 'http://www.xjrb.com/'}
        ],
        'Huizhou': [
            {"label": "Local News", "url": 'http://www.huizhou.cn/'}
        ],
        'South China Net': [
            {"label": "News", "url": 'https://news.southcn.com/'}
        ],
        'Hong Kong': [
            {"label": "Tourism Board", "url": 'https://www.discoverhongkong.com/hk-tc/what-s-new/events.html'},
            {"label": "Trade Development Council", "url": 'https://event.hktdc.com/tc/'},
            {"label": "Government Statistics", "url": 'https://www.censtatd.gov.hk/sc/'},
            {"label": "Government News", "url": 'https://www.info.gov.hk/gia/general/ctoday.htm'},
            {"label": "Tourism Network", "url": 'https://partnernet.hktb.com/en/trade_support/trade_events/conventions_exhibitions/index.html?displayMode=&viewMode=calendar&isSearch=true&keyword=&area=0&location=&from=&to=&searchMonth=--+Please+Select+--&ddlDisplayMode_selectOneMenu=All'}
        ],
        'Macau': [
            {"label": "Tourism Board", "url": 'https://www.macaotourism.gov.mo/zh-hant/events/'}
        ]
    },
    "crawl_rules": {
        "max_depth": 2,
        "max_pages": 50,
        "timeout": 15,
        "max_concurrency": 5
    },
    "content_rules": {
        "keywords": ["政策", "规划", "建设", "交通", "发展", "会议", "项目"],  # Example keywords for user input
        "future_days_threshold": 3,
        "min_content_length": 100,
        "date_formats": [
            r'\d{4}年\d{1,2}月\d{1,2}日',
            r'\d{4}-\d{2}-\d{2}',
            r'\d{4}/\d{2}/\d{2}',
            r'(?:下月|下周|明年|未来\d+天)'
        ],
        "synonyms": {
            "政策": ["条例", "法规", "办法"],
            "建设": ["建造", "修建", "施工"],
            "发展": ["开发", "推进", "促进"]
        }
    },
    "storage": {
        "output_dir": "news_data",
        "log_file": "crawl_log.jsonl"
    },
    "ui": {
        "progress_refresh": 0.5,
        "bootstrap_css": "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css",
        "font_awesome": "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
    }
}

# Setup logging
logging.basicConfig(filename='crawl_process.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class GBANewsMonitor:
    def __init__(self):
        self.visited = set()
        self.future_articles = []
        self.crawl_queue = asyncio.Queue()
        self.stop_flag = False
        self.semaphore = asyncio.Semaphore(CONFIG["crawl_rules"]["max_concurrency"])
        self.processed_pages = 0
        self.found_articles = 0
        self.user_keywords = []
        self.days_range = 1  # Default to 1 day
        self.logger = logging.getLogger(__name__)
        self.selected_cities = []
        self.filtered_entry_points = {}
        self.expanded_keywords = []
        # 初始化同义词缓存
        self.synonym_cache = {}
        # 初始化日期正则
        self.date_pattern = re.compile(
            '|'.join(CONFIG["content_rules"]["date_formats"]),
            re.IGNORECASE
        )

    def expand_keywords(self, keywords: List[str]) -> Set[str]:
        """扩展关键词带同义词和分词结果"""
        expanded = set(keywords)
        
        # 添加同义词
        for kw in keywords:
            expanded.update(CONFIG["content_rules"]["synonyms"].get(kw, []))
        
        # 分词扩展
        for kw in keywords:
            words = posseg.cut(kw)
            expanded.update(
                word.word for word in words 
                if word.flag.startswith(('n', 'v')) and len(word.word) > 1
            )
        
        return expanded

    def get_user_keywords(self):
        """Get keywords from user before starting the crawl"""
        default_keywords = ', '.join(CONFIG["content_rules"]["keywords"])
        new_kw = input(f"Enter keywords (comma-separated, use Chinese characters, example: {default_keywords}): ").strip()
        self.user_keywords = [kw.strip() for kw in new_kw.split(',') if kw.strip()]
        if not self.user_keywords:
            print("Using default keywords.")
            self.user_keywords = CONFIG["content_rules"]["keywords"]
        
        # Expand keywords
        self.expanded_keywords = self.expand_keywords(self.user_keywords)
        print(f"Keywords for search (including expansions): {', '.join(self.expanded_keywords)}")

    def get_days_range(self):
        """Get the range of days for article publication from user"""
        while True:
            try:
                days = int(input("Enter the number of days for article publication range (1-7): "))
                if 1 <= days <= 7:
                    self.days_range = days
                    print(f"Will crawl articles published within the last {days} day(s).")
                    return
                else:
                    print("Please enter a number between 1 and 7.")
            except ValueError:
                print("Please enter a valid number.")

    def get_cities_selection(self):
        """Get city selection from user"""
        cities = list(CONFIG["entry_points"].keys())
        prompt = f"Enter cities to search (comma-separated, available options: {', '.join(cities)}): "
        selected_cities = input(prompt).strip().split(',')
        
        # Filter and validate selected cities
        self.selected_cities = [city.strip() for city in selected_cities if city.strip() in cities]
        
        if not self.selected_cities:
            print("No valid city selected, using all cities.")
            self.selected_cities = cities
        else:
            print(f"Selected cities: {', '.join(self.selected_cities)}")

        # Update entry_points to only include selected cities
        self.filtered_entry_points = {city: CONFIG["entry_points"][city] for city in self.selected_cities}

    async def user_interaction(self):
        """Handle user interaction commands with enhanced output, keyword, and days range control"""
        while True:
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(None, input, "\nEnter command (stop/status/articles/future/search/keywords/days/cities): ")
                if cmd.strip().lower() == 'stop':
                    self.stop_flag = True
                    self.logger.info("User requested to stop crawler.")
                    print("\nStopping crawler...")
                    break
                elif cmd.strip().lower() == 'status':
                    self.logger.info(f"Status check: Processed {self.processed_pages} pages, found {self.found_articles} articles.")
                    print(f"\n[Status]\n"
                          f"  Processed Pages: {self.processed_pages}\n"
                          f"  Articles Found: {self.found_articles}\n"
                          f"  Queue Size: {self.crawl_queue.qsize()}\n"
                          f"  Concurrency: {self.semaphore._value}/{CONFIG['crawl_rules']['max_concurrency']}")
                elif cmd.strip().lower() == 'articles':
                    self.logger.info(f"Displaying articles list.")
                    print(f"\n[Articles]\n"
                          f"  Total Articles Found: {self.found_articles}\n"
                          f"  Example Article URLs:")
                    for i, article in enumerate(self.future_articles[:5], 1):
                        print(f"    {i}. {article['url']}")
                    if len(self.future_articles) > 5:
                        print("    ...and more")
                elif cmd.strip().lower() == 'future':
                    self.logger.info(f"Displaying future articles.")
                    print(f"\n[Future Articles]\n"
                          f"  Number of Future Articles: {len(self.future_articles)}")
                    for article in self.future_articles[:3]:
                        print(f"    URL: {article['url']}, Date: {article['pub_date']}")
                    if len(self.future_articles) > 3:
                        print("    ...additional future articles exist")
                elif cmd.strip().lower() == 'search':
                    if not self.user_keywords:
                        print("Please add keywords first. Example keywords: 政策, 规划, 建设, 交通, 发展, 会议, 项目")
                    else:
                        found = [a for a in self.future_articles if any(kw in a['content'] for kw in self.expanded_keywords)]
                        print(f"\n[Searched Articles]\n"
                              f"  Articles Matched: {len(found)}\n"
                              f"  Example URLs:")
                        for i, article in enumerate(found[:5], 1):
                            print(f"    {i}. {article['url']}")
                        if len(found) > 5:
                            print("    ...and more")
                elif cmd.strip().lower() == 'keywords':
                    new_kw = input("Enter new keywords (comma-separated, use Chinese characters): ").strip().split(',')
                    self.user_keywords.extend([kw.strip() for kw in new_kw if kw.strip()])
                    self.expanded_keywords = self.expand_keywords(self.user_keywords)
                    print(f"Current keywords (including expansions): {', '.join(self.expanded_keywords)}")
                    print("Example keywords for reference: 政策, 规划, 建设, 交通, 发展, 会议, 项目")
                elif cmd.strip().lower() == 'days':
                    self.get_days_range()
                elif cmd.strip().lower() == 'cities':
                    self.get_cities_selection()
                else:
                    print("\nUnknown command. Use 'stop', 'status', 'articles', 'future', 'search', 'keywords', 'days', or 'cities'.")
            except asyncio.CancelledError:
                self.logger.warning("User interaction loop was cancelled.")
                return

    async def show_progress(self):
        """Display crawl progress in real-time"""
        while not self.stop_flag:
            print(f"\r[Progress] Pages: {self.processed_pages} | Articles: {self.found_articles} | Queue: {self.crawl_queue.qsize()}", end="")
            await asyncio.sleep(CONFIG["ui"]["progress_refresh"])
        print("\n")

    def generate_fingerprint(self, text):
        """Generate content fingerprint for deduplication"""
        features = jieba.cut(text)
        return Simhash(' '.join(features)).value

    async def fetch_page(self, session, url):
        """Fetch web page content with logging"""
        async with self.semaphore:
            try:
                async with session.get(url, timeout=CONFIG["crawl_rules"]["timeout"]) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        self.logger.warning(f"Fetching {url} failed with status code: {response.status}")
            except Exception as e:
                self.logger.error(f"Error fetching {url}: {str(e)}")
                self.log_operation({"url": url, "error": str(e)})
            return None

    def extract_links(self, html, base_url):
        """Extract links from page content"""
        soup = BeautifulSoup(html, 'html.parser')
        links = set()

        for a in soup.find_all('a', href=True):
            href = urljoin(base_url, a['href'])
            if href not in self.visited:
                links.add(href)
        return list(links)

    def parse_content(self, html, url) -> Dict:
        """Parse page content, including sentences with future dates"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 优先提取正文内容
        main_content = soup.find('div', class_=re.compile('content|main|article'))
        content = main_content.get_text() if main_content else soup.get_text()
        
        # 提取图片
        images = [
            urljoin(url, img['src']) 
            for img in soup.find_all('img', src=True)
            if img['src'].lower().endswith(('.jpg', '.png', '.jpeg'))
        ][:3]  # 取前3张图片
        
        # 优化日期解析
        pub_date = self._parse_date(soup)
        
        # 提取未来日期句子（优化版）
        future_sentences = self._extract_future_sentences(content, pub_date)
        
        return {
            "title": soup.title.string.strip() if soup.title else "无标题",
            "content": content.strip(),
            "pub_date": pub_date,
            "url": url,
            "images": images,
            "future_sentences": future_sentences
        }

    def _extract_future_sentences(self, text: str, base_date: datetime) -> List[str]:
        """高效提取含未来日期的句子"""
        sentences = []
        now = datetime.now()
        threshold_date = now + timedelta(days=CONFIG["content_rules"]["future_days_threshold"])
        
        for sentence in re.split(r'[。！？]', text):
            if not sentence:
                continue
                
            # 绝对日期检测
            absolute_dates = self.date_pattern.findall(sentence)
            if any(self.parse_date(d) > threshold_date for d in absolute_dates):
                sentences.append(sentence.strip())
                continue
                
            # 相对日期检测
            if re.search(r'(下月|下周|明年|未来\d+天)', sentence):
                sentences.append(sentence.strip())
        
        return sentences

    def _parse_date(self, soup: BeautifulSoup) -> datetime:
        """多重日期解析策略"""
        # 策略1：从meta信息获取
        meta_date = soup.find('meta', {'property': 'article:published_time'})
        if meta_date:
            return dateparser.parse(meta_date['content'])
        
        # 策略2：从特定class获取
        date_element = soup.find(class_=re.compile('date|time|pub-date'))
        if date_element:
            return self.parse_date(date_element.get_text())
        
        # 策略3：从正文中搜索
        return self.parse_date(self.date_pattern.search(soup.get_text()))

    def detect_future_dates(self, article):
        """Detect future dates in content"""
        if not article['pub_date']:
            return False

        future_dates = []
        base_date = article['pub_date']

        absolute_dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', article['content'])
        for d in absolute_dates:
            dt = dateparser.parse(d, languages=['zh'])
            if dt and dt > base_date + timedelta(days=CONFIG["content_rules"]["future_days_threshold"]):
                future_dates.append(dt)

        relative_phrases = re.findall(r'(下月|下周|明年|未来\d+天)', article['content'])
        for phrase in relative_phrases:
            if '下月' in phrase:
                future_dates.append(base_date + timedelta(days=30))
            elif '下周' in phrase:
                future_dates.append(base_date + timedelta(days=7))

        return len(future_dates) > 0

    async def process_page(self, session, url, depth):
        """Process a single page with logging, considering user-specified days range"""
        if self.stop_flag or depth > CONFIG["crawl_rules"]["max_depth"]:
            return

        if url in self.visited:
            return
        self.visited.add(url)

        self.logger.info(f"Processing page: {url} at depth {depth}")
        html = await self.fetch_page(session, url)
        if not html:
            return

        article = self.parse_content(html, url)
        if article:
            # Check if the article's publication date is within the user-specified range
            if self.is_within_days_range(article['pub_date']):
                if self.detect_future_dates(article):  # Check for future dates here
                    # Check both title and content for keywords
                    if any(kw in article['title'].lower() or kw in article['content'].lower() for kw in self.expanded_keywords):
                        self.save_article(article)
                        self.found_articles += 1
                        self.future_articles.append(article)
                        self.logger.info(f"Article saved: {url}")

        if depth < CONFIG["crawl_rules"]["max_depth"]:
            links = self.extract_links(html, url)
            for link in links[:CONFIG["crawl_rules"]["max_pages"] // (depth+1)]:
                await self.crawl_queue.put((link, depth+1))

        self.processed_pages += 1

    def is_within_days_range(self, pub_date):
        """Check if the publication date is within the user-specified range"""
        today = datetime.now().date()
        days_ago = today - timedelta(days=self.days_range - 1)
        return days_ago <= pub_date.date() <= today

    def save_article(self, article):
        """Save article to file"""
        filename = f"article_{hashlib.md5(article['url'].encode()).hexdigest()}.json"
        path = os.path.join(CONFIG["storage"]["output_dir"], filename)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "meta": {
                    "url": article['url'],
                    "pub_date": article['pub_date'].isoformat()
                },
                "content": article['content']
            }, f, ensure_ascii=False)

    def log_operation(self, log_entry):
        """Log operations"""
        with open(CONFIG["storage"]["log_file"], 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    async def task_dispatcher(self, session):
        """Task dispatcher"""
        for city, urls in self.filtered_entry_points.items():
            for link in urls:
                await self.crawl_queue.put((link['url'], 0))

        while not self.stop_flag and not self.crawl_queue.empty():
            url, depth = await self.crawl_queue.get()
            await self.process_page(session, url, depth)

        await self.crawl_queue.join()

    def generate_report(self):
        """Generate a report after crawling including an HTML file with future articles and sentences."""
        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>大湾区新闻监测报告</title>
    <link href="{{ config_ui_bootstrap_css }}" rel="stylesheet">
    <link href="{{ config_ui_font_awesome }}" rel="stylesheet">
    <style>
        .article-card {
            transition: transform 0.2s;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .article-card:hover {
            transform: translateY(-5px);
        }
        .future-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            font-size: 0.8rem;
        }
        .news-image {
            height: 200px;
            object-fit: cover;
            border-radius: 10px 10px 0 0;
        }
        .keyword-highlight {
            color: #dc3545;
            font-weight: bold;
        }
    </style>
</head>
<body class="bg-light">
    <div class="container py-5">
        <h1 class="mb-4 text-center"><i class="fas fa-newspaper me-2"></i>大湾区新闻监测报告</h1>
        
        <div class="row g-4">
            <!-- 统计卡片 -->
            <div class="col-md-4">
                <div class="card article-card h-100">
                    <div class="card-body">
                        <h5><i class="fas fa-chart-bar me-2"></i>统计概览</h5>
                        <ul class="list-unstyled">
                            <li>已处理页面: {{ processed_pages }}</li>
                            <li>发现文章数: {{ found_articles }}</li>
                            <li>未来事件文章: {{ future_articles_count }}</li>
                        </ul>
                    </div>
                </div>
            </div>

            <!-- 文章列表 -->
            {% for article in future_articles %}
            <div class="col-md-6">
                <div class="card article-card h-100">
                    {% if article.images %}
                    <img src="{{ article.images[0] }}" class="card-img-top news-image" 
                         alt="新闻配图" onerror="this.style.display='none'">
                    {% endif %}
                    
                    <div class="card-body">
                        <span class="badge bg-danger future-badge">
                            <i class="fas fa-calendar-alt me-1"></i>未来事件
                        </span>
                        
                        <h5 class="card-title">
                            <a href="{{ article.url }}" target="_blank" 
                               class="text-decoration-none text-dark">
                               {{ article.title }}
                            </a>
                        </h5>
                        
                        <div class="mb-2">
                            <small class="text-muted">
                                <i class="fas fa-clock me-1"></i>
                                {{ article.pub_date.strftime('%Y-%m-%d %H:%M') }}
                            </small>
                        </div>

                        <!-- 关键词高亮 -->
                        <div class="card-text">
                            {% for sentence in article.future_sentences %}
                            <p class="mb-2">
                                {% for word in jieba.cut(sentence) %}
                                    {% if word in expanded_keywords %}
                                    <span class="keyword-highlight">{{ word }}</span>
                                    {% else %}
                                    {{ word }}
                                    {% endif %}
                                {% endfor %}
                                <a href="{{ article.url }}" target="_blank" 
                                   class="text-decoration-none ms-2">
                                   <i class="fas fa-external-link-alt"></i>
                                </a>
                            </p>
                            {% endfor %}
                        </div>

                        <!-- 图片缩略图 -->
                        {% if article.images %}
                        <div class="mt-3 d-flex gap-2 flex-wrap">
                            {% for img in article.images[1:] %}
                            <a href="{{ img }}" target="_blank">
                                <img src="{{ img }}" class="rounded" 
                                     style="height:50px; width:auto;">
                            </a>
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

        # 使用Jinja2模板引擎（需要安装）
        report_path = os.path.join(CONFIG["storage"]["output_dir"], "report.html")

        with open(report_path, 'w', encoding='utf-8') as f:
            # Capture the rendered output
            rendered_html = Template(html_template).render(
                future_articles=self.future_articles,
                expanded_keywords=self.expanded_keywords,
                jieba=jieba,
                config_ui_bootstrap_css=CONFIG['ui']['bootstrap_css'],
                config_ui_font_awesome=CONFIG['ui']['font_awesome'],
                processed_pages=self.processed_pages,
                found_articles=self.found_articles,
                future_articles_count=len(self.future_articles)
            )
            # Write the rendered HTML to the file
            f.write(rendered_html)

        self.logger.info(f"生成可视化报告：{report_path}")

    async def run(self):
        """Main run function"""
        self.get_user_keywords()
        self.get_days_range()
        self.get_cities_selection()
        input("Press Enter to start crawling...")  # Wait for user to press Enter
        
        try:
            async with aiohttp.ClientSession() as session:
                self.stop_flag = False
                await asyncio.gather(
                    self.task_dispatcher(session),
                    self.user_interaction(),
                    self.show_progress()
                )
        except asyncio.CancelledError:
            self.logger.warning("Crawler was forcibly stopped.")
        finally:
            self.generate_report()
            print(f"\nProcessed {self.processed_pages} pages and found {self.found_articles} articles.")

if __name__ == "__main__":
    monitor = GBANewsMonitor()
    asyncio.run(monitor.run())