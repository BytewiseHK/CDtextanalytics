import asyncio
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
from apscheduler.schedulers.background import BackgroundScheduler

# 配置参数
CONFIG = {
    "sources": {
        "广州": "https://news.dayoo.com/guangzhou/",
        "深圳": "https://www.sznews.com/news/",
        "珠海": "https://www.hizh.cn/"
    },
    "keywords": ["政策", "峰会", "基建", "交通", "规划", "发展", "GDP"],
    "output_dir": "GBA_News",
    "max_concurrency": 8,
    "timeout": 15,
    "log_file": "process_report.log"
}

class EnhancedNewsCrawler:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(CONFIG["max_concurrency"])
        self.fingerprints = set()
        self.future_articles = []
        self.current_date = datetime.now()
        
        # 初始化日志
        with open(CONFIG["log_file"], "w", encoding="utf-8") as f:
            f.write("大湾区新闻简报生成流程记录\n\n")
            f.write(f"开始时间：{self.current_date.strftime('%Y-%m-%d %H:%M')}\n")
            f.write("="*50 + "\n")

    async def fetch(self, session, url):
        """异步获取页面内容"""
        async with self.semaphore:
            try:
                async with session.get(url, timeout=CONFIG["timeout"]) as response:
                    content = await response.text()
                    self.log_process(f"抓取成功：{url}")
                    return str(content)
            except Exception as e:
                self.log_process(f"抓取失败：{url} - {str(e)}")
                return None

    def log_process(self, message):
        """记录处理流程"""
        with open(CONFIG["log_file"], "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")


    def log_curated_info(self, articles):
        """记录策划信息"""
        with open("curated_info.txt", "w", encoding="utf-8") as f:
            f.write("手动策划信息记录\n\n")
            for article in articles:
                f.write(f"标题: {article['title']}\n")
                f.write(f"链接: {article['url']}\n")
                f.write(f"城市: {article['city']}\n")
                f.write("未来日期: " + ", ".join(d['formatted'] for d in article['future_dates']) + "\n")
                f.write("=" * 50 + "\n")

    def is_news_url(self, url):
        """URL有效性验证"""
        patterns = [
            r"/\d{4}-\d{2}/\d{2}/",
            r"/content_\d+\.htm",
            r"_2025\d{4}/"
        ]
        return any(re.search(p, url) for p in patterns)

    async def extract_news(self, session, url):
        content = await self.fetch(session, url)
        if not content:
            return

        # 计算Simhash值
        simhash = Simhash(content)
        hash_value = simhash.value  # 提取哈希值（整数）

        # 去重检测
        if any(Simhash(value=existing).distance(simhash) < 3 for existing in self.fingerprints):
            self.log_process(f"重复内容跳过：{url}")
            return
        self.fingerprints.add(hash_value)  # 存储哈希值

    # 后续处理...

        # 解析内容
        soup = BeautifulSoup(content, 'html.parser')
        article = {
            "title": self.get_title(soup),
            "content": self.get_content(soup),
            "publish_date": self.get_publish_date(soup),
            "url": url,
            "city": self.detect_city(url),
            "future_dates": []
        }

        # 关键词筛选和未来日期检测
        if self.is_valid_article(article):
            article["future_dates"] = self.detect_future_dates(article["content"])
            if article["future_dates"]:
                self.future_articles.append(article)
                self.log_process(f"发现未来事件：{article['title']}")

    def detect_city(self, url):
        """根据URL检测城市"""
        for city in CONFIG["sources"]:
            if city in url:
                return city
        return "其他"

    def is_valid_article(self, article):
        """有效性验证"""
        # 关键词匹配
        keyword_check = any(
            kw in article["title"] or kw in article["content"]
            for kw in CONFIG["keywords"]
        )
        
        # 基本内容验证
        content_check = len(article["content"] or "") > 200
        
        return keyword_check and content_check and article["future_dates"]

    def get_title(self, soup):
        title_selector = 'h1'  # Update the selector based on the HTML structure
        title_element = soup.select_one(title_selector)
        return title_element.text.strip() if title_element else "No Title Found"

    def get_content(self, soup):
        content_selector = '.article-content p'  # Adjust based on actual HTML structure
        paragraphs = soup.select(content_selector)
        return ' '.join(p.text.strip() for p in paragraphs)

    def get_publish_date(self, soup):
        date_selector = '.publish-date'  # Adjust based on actual HTML structure
        date_element = soup.select_one(date_selector)
        return date_element.text.strip() if date_element else None

    def detect_future_dates(self, content):
        """未来日期检测"""
        settings = {
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': self.current_date,
            'LANGUAGES': ['zh']
        }
        
        date_patterns = [
            (r'(\d{4}年\d{1,2}月\d{1,2}日)', '%Y年%m月%d日'),
            (r'(\d{4}-\d{1,2}-\d{1,2})', '%Y-%m-%d'),
            (r'(明年[一二]季度)', '相对日期'),
            (r'([下本]月\d{1,2}号)', '相对日期')
        ]
        
        found_dates = []
        for pattern, fmt in date_patterns:
            for match in re.finditer(pattern, content):
                date_str = match.group(1)
                try:
                    dt = dateparser.parse(date_str, settings=settings)
                    if dt and dt > self.current_date + timedelta(days=1):
                        found_dates.append({
                            "date_str": date_str,
                            "formatted": dt.strftime("%Y-%m-%d"),
                            "context": content[max(0, match.start()-50):match.end()+50]
                        })
                except:
                    continue
        return found_dates

    def generate_html_report(self):
        """生成美化后的HTML报告"""
        os.makedirs(CONFIG["output_dir"], exist_ok=True)
        filename = f"GBA_News_{self.current_date.strftime('%Y%m%d_%H%M')}.html"
        filepath = os.path.join(CONFIG["output_dir"], filename)

        style = """
        <style>
            body { font-family: 'Segoe UI', sans-serif; margin: 2rem; }
            .header { 
                background: #2c3e50; 
                color: white; 
                padding: 2rem; 
                border-radius: 10px;
                margin-bottom: 2rem;
            }
            .article {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 1.5rem;
                margin-bottom: 1.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .city-tag {
                background: #3498db;
                color: white;
                padding: 0.3rem 0.8rem;
                border-radius: 15px;
                font-size: 0.9rem;
                display: inline-block;
                margin: 0.5rem 0;
            }
            .date-badge {
                background: #27ae60;
                color: white;
                padding: 0.2rem 0.6rem;
                border-radius: 12px;
                font-size: 0.85rem;
            }
            a { color: #2980b9; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
        """

        articles_html = ""
        for article in self.future_articles:
            dates_html = "".join(
                f'<span class="date-badge">{d["formatted"]}</span> '
                for d in article["future_dates"]
            )
            
            articles_html += f"""
            <div class="article">
                <h3>{article['title']}</h3>
                <div class="city-tag">{article['city']}</div>
                <div class="meta">
                    <p>来源：<a href="{article['url']}" target="_blank">{article['url']}</a></p>
                    <p>检测到未来日期：{dates_html}</p>
                </div>
                <div class="content">
                    <p>{article['content'][:500]}...</p>
                </div>
            </div>
            """

        html_content = f"""
        <html>
        <head>
            <title>大湾区未来事件简报 {self.current_date.strftime('%Y-%m-%d')}</title>
            <meta charset="utf-8">
            {style}
        </head>
        <body>
            <div class="header">
                <h1>粤港澳大湾区未来事件简报</h1>
                <p>生成时间：{self.current_date.strftime('%Y-%m-%d %H:%M')}</p>
                <p>共发现 {len(self.future_articles)} 条未来事件新闻</p>
            </div>
            {articles_html}
        </body>
        </html>
        """

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.log_process(f"生成报告文件：{filepath}")

async def main():
    crawler = EnhancedNewsCrawler()
    async with aiohttp.ClientSession() as session:
        tasks = []
        for city, base_url in CONFIG["sources"].items():
            crawler.log_process(f"开始处理城市源：{city} ({base_url})")
            main_page = await crawler.fetch(session, base_url)
            if not main_page:
                continue

            soup = BeautifulSoup(main_page, 'html.parser')
            links = [urljoin(base_url, a['href']) for a in soup.find_all('a', href=True)]
            
            for url in links:
                if crawler.is_news_url(url):
                    task = asyncio.create_task(crawler.extract_news(session, url))  # 使用 create_task
                    tasks.append(task)
            
            await asyncio.gather(*tasks)
    
    crawler.generate_html_report()
    crawler.log_curated_info(crawler.future_articles)  # 记录策划信息
    crawler.log_process("处理流程完成")

# 定时任务配置
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: asyncio.run(main()), 'cron', hour=8)

if __name__ == "__main__":
    asyncio.run(main())