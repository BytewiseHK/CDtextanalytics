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
            {"label": "Main News", "url": "https://www.hizh.cn/"}
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
        "min_content_length": 100
    },
    "storage": {
        "output_dir": "news_data",
        "log_file": "crawl_log.jsonl"
    },
    "ui": {
        "progress_refresh": 0.5
    }
}

# Setup logging
logging.basicConfig(filename='crawl_process.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def expand_keywords(keywords):
    """Expand keywords with similar terms or synonyms"""
    expanded_keywords = set(keywords)
    for keyword in keywords:
        for word, flag in posseg.cut(keyword):
            if flag in ['n', 'v']:  # Nouns and verbs might have synonyms or be used in similar contexts
                expanded_keywords.add(word)
        # Here you would add logic to look up synonyms or similar terms from a dictionary or API
    
    return list(expanded_keywords)

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

    def get_user_keywords(self):
        """Get keywords from user before starting the crawl"""
        default_keywords = ', '.join(CONFIG["content_rules"]["keywords"])
        new_kw = input(f"Enter keywords (comma-separated, use Chinese characters, example: {default_keywords}): ").strip()
        self.user_keywords = [kw.strip() for kw in new_kw.split(',') if kw.strip()]
        if not self.user_keywords:
            print("Using default keywords.")
            self.user_keywords = CONFIG["content_rules"]["keywords"]
        
        # Expand keywords
        self.expanded_keywords = expand_keywords(self.user_keywords)
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
                    self.expanded_keywords = expand_keywords(self.user_keywords)
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

    def parse_content(self, html, url):
        """Parse page content, including sentences with future dates"""
        soup = BeautifulSoup(html, 'html.parser')
        content = soup.get_text()
        title = soup.title.string if soup.title else "No Title"
        
        # Extract images
        images = [img['src'] for img in soup.find_all('img', src=True)[:1]]  # Just get the first image

        # Combine content and title for keyword search
        text_to_search = f"{title} {content}"
        
        if len(text_to_search) < CONFIG["content_rules"]["min_content_length"]:
            return None

        # Detect ads or repetitive content
        if "广告" in content or len(set(content.split())) < 20:
            return None

        # Extract date from content. Generalize regex for different date formats
        date_match = re.search(r'\b(?:19|20)\d{2}[-\/年]\d{1,2}[-\/月]\d{1,2}\b', text_to_search)
        if date_match:
            pub_date_str = date_match.group()
            # Convert 年/月 format to - for dateparser
            pub_date_str = pub_date_str.replace('年', '-').replace('月', '-').replace('/', '-')
            pub_date = self.parse_date(pub_date_str)
        else:
            pub_date = datetime.now()  # Fallback to current date if no date found

        # Find sentences with future dates
        future_sentences = []
        sentences = re.split(r'[。？！]', content)  # Split into sentences using Chinese punctuation
        for sentence in sentences:
            if self.detect_future_dates({'content': sentence, 'pub_date': pub_date}):
                future_sentences.append(sentence.strip())
                break

        return {
            "title": title,
            "content": content,
            "pub_date": pub_date,
            "url": url,
            "images": images,
            "future_sentences": future_sentences[:1]
        }

    def parse_date(self, date_str):
        """Parse date string"""
        settings = {'PREFER_DAY_OF_MONTH': 'first', 'RELATIVE_BASE': datetime.now()}
        return dateparser.parse(date_str, settings=settings, languages=['zh'])

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

    from jinja2 import Template

    def generate_report(self):
        """Generate a report after crawling including an HTML file with future articles and sentences."""
        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>大湾区新闻监测报告</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .news-card {
            margin-bottom: 20px;
            transition: transform 0.3s;
        }
        .news-card:hover {
            transform: scale(1.02);
        }
        .card-title a {
            color: #333;
        }
        .card-title a:hover {
            color: #007bff;
            text-decoration: none;
        }
        .news-image {
            max-height: 200px;
            object-fit: cover;
        }
        .keyword-highlight {
            background-color: #ffeeba;
            padding: 0 2px;
        }
    </style>
</head>
<body class="bg-light">
    <div class="container py-5">
        <h1 class="mb-4 text-center"><i class="fas fa-newspaper me-2"></i>大湾区新闻监测报告</h1>
        
        <div class="row">
            <div class="col-md-4 mb-4">
                <div class="card news-card h-100">
                    <div class="card-body">
                        <h5 class="card-title"><i class="fas fa-chart-bar me-2"></i>统计概览</h5>
                        <ul class="list-unstyled">
                            <li>已处理页面: {{ processed_pages }}</li>
                            <li>发现文章数: {{ found_articles }}</li>
                            <li>未来事件文章: {{ future_articles_count }}</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            {% for article in future_articles %}
            <div class="col-md-6 mb-4">
                <div class="card news-card h-100">
                    {% if article.images %}
                    <img src="{{ article.images[0] }}" class="card-img-top news-image" alt="新闻配图">
                    {% endif %}
                    <div class="card-body">
                        <h5 class="card-title">
                            <a href="{{ article.url }}" target="_blank">
                                {{ article.title }}
                            </a>
                        </h5>
                        <p class="card-text">
                            <small class="text-muted">
                                <i class="fas fa-clock me-1"></i>
                                {{ article.pub_date.strftime('%Y-%m-%d %H:%M') }}
                            </small>
                        </p>
                        <div class="card-text">
                            {% for sentence in article.future_sentences %}
                            <p>
                            {% set sentence = article.future_sentences[0] %}
                            {% for word in jieba.cut(sentence) %}
                                {% if word in expanded_keywords %}
                                <span class="keyword-highlight">{{ word }}</span>
                                {% else %}
                                {{ word }}
                                {% endif %}
                            {% endfor %}
                            </p>
                            {% endfor %}
                        </div>
                        <a href="{{ article.url }}" class="btn btn-outline-primary btn-sm" target="_blank">阅读全文</a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
        """

        report_path = os.path.join(CONFIG["storage"]["output_dir"], "report.html")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            rendered_html = Template(html_template).render(
                future_articles=self.future_articles,
                expanded_keywords=self.expanded_keywords,
                jieba=jieba,
                processed_pages=self.processed_pages,
                found_articles=self.found_articles,
                future_articles_count=len(self.future_articles)
            )
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