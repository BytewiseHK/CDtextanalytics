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

# Configuration parameters
CONFIG = {
    "entry_points": {
        "Guangzhou": "https://news.dayoo.com/guangzhou/",
        "Shenzhen": "https://www.sznews.com/news/",
        "Zhuhai": "https://news.hizh.cn/"
    },
    "crawl_rules": {
        "max_depth": 2,
        "max_pages": 50,
        "timeout": 15,
        "max_concurrency": 5
    },
    "content_rules": {
        "keywords": ["政策", "规划", "建设", "交通", "发展", "会议", "项目"],
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

class GBANewsMonitor:
    def __init__(self):
        self.visited = set()
        self.future_articles = []
        self.crawl_queue = asyncio.Queue()
        self.stop_flag = False
        self.semaphore = asyncio.Semaphore(CONFIG["crawl_rules"]["max_concurrency"])
        self.processed_pages = 0
        self.found_articles = 0

        # Initialize storage directory
        os.makedirs(CONFIG["storage"]["output_dir"], exist_ok=True)
        self.logger = logging.getLogger(__name__)

    async def user_interaction(self):
        """Handle user interaction commands with enhanced output"""
        while True:
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(None, input, "\nEnter command (stop/status/articles/future): ")
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
                else:
                    print("\nUnknown command. Use 'stop', 'status', 'articles', or 'future'.")
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
        """Parse page content"""
        soup = BeautifulSoup(html, 'html.parser')
        content = soup.get_text()
        if len(content) < CONFIG["content_rules"]["min_content_length"]:
            return None

        # Detect ads or repetitive content
        if "广告" in content or len(set(content.split())) < 20:  # Simple check for ads or repetitive text
            return None

        # Here we're assuming the title can be extracted from the HTML. Adjust as needed.
        title = soup.title.string if soup.title else "No Title"  # Or use some other method to get the title
        pub_date = datetime.now()  # Since we can't parse, we use current time for demonstration
        return {
            "title": title,
            "content": content,
            "pub_date": pub_date,
            "url": url,
        }

    def parse_date(self, date_str):
        """Parse date string"""
        settings = {'PREFER_DAY_OF_MONTH': 'first', 'RELATIVE_BASE': datetime.now(), 'LANGUAGES': ['zh']}
        return dateparser.parse(date_str, settings=settings)

    def detect_future_dates(self, article):
        """Detect future dates in content"""
        if not article['pub_date']:
            return False

        future_dates = []
        base_date = article['pub_date']

        absolute_dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', article['content'])
        for d in absolute_dates:
            dt = dateparser.parse(d)
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
        """Process a single page with logging"""
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
        if article and any(kw in article['content'] for kw in CONFIG["content_rules"]["keywords"]):
            if self.detect_future_dates(article):
                self.save_article(article)
                self.found_articles += 1
                self.future_articles.append(article)
                self.logger.info(f"Article saved: {url}")

        if depth < CONFIG["crawl_rules"]["max_depth"]:
            links = self.extract_links(html, url)
            for link in links[:CONFIG["crawl_rules"]["max_pages"] // (depth+1)]:
                await self.crawl_queue.put((link, depth+1))

        self.processed_pages += 1

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
        for url in CONFIG["entry_points"].values():
            await self.crawl_queue.put((url, 0))

        while not self.stop_flag and not self.crawl_queue.empty():
            url, depth = await self.crawl_queue.get()
            await self.process_page(session, url, depth)

        await self.crawl_queue.join()

    def generate_report(self):
        """Generate a report after crawling including an HTML file with future articles"""
        # Text report
        report_path = os.path.join(CONFIG["storage"]["output_dir"], "report.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"Total Pages Processed: {self.processed_pages}\n")
            f.write(f"Articles Found: {self.found_articles}\n")
            f.write(f"Future Articles: {len(self.future_articles)}\n")
        self.logger.info(f"Text report generated at {report_path}")

        # HTML report for future articles
        html_report_name = f"future_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_report_path = os.path.join(CONFIG["storage"]["output_dir"], html_report_name)
        
        with open(html_report_path, 'w', encoding='utf-8') as html_file:
            html_file.write("<!DOCTYPE html><html><head><title>Future Articles Report</title></head><body>")
            html_file.write("<h1>Future Articles Report</h1>")
            html_file.write("<ul>")
            for article in self.future_articles:
                title = article.get('title', 'No Title')  # Assuming title is available or default to 'No Title'
                url = article['url']
                html_file.write(f'<li><a href="{url}" target="_blank">{title}</a></li>')
            html_file.write("</ul></body></html>")
        
        self.logger.info(f"HTML report for future articles generated at {html_report_path}")

    async def run(self):
        """Main run function"""
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