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
import feedparser
import smtplib
from email.mime.text import MIMEText
import itchat
import schedule
import time

# Configuration parameters
CONFIG = {
    "rss_sources": [
        "https://example.com/rss",  # 替换为您的 RSS 源
    ],
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
    "email": {
        "address": "your_email@example.com",
        "password": "your_email_password",
        "recipient": "recipient@example.com"
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
        itchat.auto_login()  # 微信登录

    async def fetch_rss_articles(self):
        """Fetch articles from RSS sources"""
        for rss_url in CONFIG["rss_sources"]:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                title = entry.title
                link = entry.link
                summary = entry.summary
                pub_date = datetime.now()  # 使用当前时间，或根据需要解析

                # 过滤关键字
                if any(keyword in title for keyword in CONFIG["content_rules"]["keywords"]):
                    article = {
                        "title": title,
                        "url": link,
                        "summary": summary,
                        "pub_date": pub_date
                    }
                    self.future_articles.append(article)
                    self.found_articles += 1
                    self.logger.info(f"Fetched RSS article: {title}")

    async def send_email(self, message):
        """Send email with the collected articles"""
        msg = MIMEText(message)
        msg['Subject'] = '每日新闻'
        msg['From'] = CONFIG["email"]["address"]
        msg['To'] = CONFIG["email"]["recipient"]

        with smtplib.SMTP_SSL('smtp.example.com', 465) as server:  # 修改为您的SMTP服务器
            server.login(CONFIG["email"]["address"], CONFIG["email"]["password"])
            server.send_message(msg)
    
    async def send_to_wechat(self, message):
        """Send message to WeChat"""
        itchat.send(message, toUserName='filehelper')  # 发送到文件助手

    async def fetch_and_send_news(self):
        """Fetch news articles and send them out"""
        await self.fetch_rss_articles()
        if self.future_articles:
            message = "今日新闻:\n" + "\n".join(
                [f"标题: {article['title']}\n链接: {article['url']}\n摘要: {article['summary']}\n" for article in self.future_articles]
            )
            await self.send_email(message)
            await self.send_to_wechat(message)

    async def run(self):
        """Main run function"""
        await self.fetch_and_send_news()
        self.logger.info("News fetched and sent.")

if __name__ == "__main__":
    monitor = GBANewsMonitor()
    schedule.every().day.at("09:00").do(lambda: asyncio.run(monitor.run()))

    while True:
        schedule.run_pending()
        time.sleep(1)