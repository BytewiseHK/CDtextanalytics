import aiohttp
import re
import json
import heapq
import os
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin,urlparse, parse_qs, urlunparse, urlencode
from bs4 import BeautifulSoup
from simhash import Simhash
import dateparser
import jieba
import asyncio
import logging
from jieba import posseg
from jinja2 import Template
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from transformers import pipeline  # 新增NLP模型
from readability import Document  # 新增正文提取
from playwright.async_api import async_playwright  # 新增浏览器渲染
from pybloom_live import ScalableBloomFilter

class YourSpider:
    def __init__(self):
        self.url_filter = ScalableBloomFilter(
            initial_capacity=10000, 
            error_rate=0.001,
            mode=ScalableBloomFilter.LARGE_SET_GROWTH
        )
        
    def normalize_url(self, url):
        """增强型URL规范化"""
        try:
            parsed = urlparse(url)
            
            # 参数过滤
            filtered_params = {}
            for k, v in parse_qs(parsed.query).items():
                if k not in ['utm_source', 'from', 'spm']:
                    filtered_params[k] = v
            
            # 路径标准化
            path = parsed.path.rstrip('/')
            
            # 构建新URL
            return urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                path,
                parsed.params,
                urlencode(filtered_params, doseq=True),
                parsed.fragment
            ))
        except Exception as e:
            self.logger.error(f"URL规范化失败：{url} - {str(e)}")
            return url
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
        "max_depth": 3,
        "max_pages": 1000,
        "timeout": 15,
        "max_concurrency": 5,
        "dynamic_render": True,  # 新增动态渲染开关
        "request_interval": {  # 新增请求间隔配置
            "base": 1.0,
            "random_range": 0.5
        }
    },
    "content_rules": {
        "keywords": ["政策", "规划", "建设", "交通", "发展", "会议", "项目"],  # Example keywords for user input
        "future_days_threshold": 3,
        "min_content_length": 2000,
        "content_validation": {
            "min_length": 2000,  # 内容页最小长度
            "selectors": ['.article-content', '#content', 'div.content', 'main']
        }
    },
    "storage": {
        "output_dir": "news_data",
        "log_file": "crawl_log.jsonl"
    },
    "ui": {
        "progress_refresh": 0.5
    },
    "retry_policy": {  # 新增重试策略
        "max_retries": 3,
        "backoff_factor": 0.5,
        "status_forcelist": [500, 502, 503, 504]
    }
}
# Setup logging
logging.basicConfig(filename='crawl_process.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
# Synonym dictionary for future date detection
FUTURE_DATE_SYNONYMS = {
    "下月": ["下个月", "下個月", "下月"],
    "下周": ["下个星期", "下星期", "下周"],
    "明年": ["來年", "来年", "明年"],
    "未来": ["未來", "未来", "後來", "后来"],
    "近期": ["近期", "即將", "即将", "即將要", "即将要"],
    "後年": ["后年"],
    "不久": ["不久", "不久後", "不久后"]
    # Add more as needed
}
def expand_keywords(keywords):
    """Expand keywords with similar terms or synonyms"""
    synonym_db = {
        "科技": ["技术", "创新", "研发", "高科技", "高新技术"],
        "发展": ["建设", "推进", "促进", "规划", "实施"]
    }
    
    expanded = set(keywords)
    for kw in keywords:
        expanded.update(synonym_db.get(kw, []))
        # 添加词性扩展
        for word, flag in posseg.cut(kw):
            if flag.startswith('n'):
                expanded.add(f"{word}发展")  # 组合词
    return list(expanded)


class ContentAnalyzer:
    """新增NLP分析模块"""
    def __init__(self):
        self.keyword_extractor = pipeline("ner", model="bert-base-chinese")
        self.summarizer = pipeline("summarization")
    
    def analyze(self, text):
        return {
            "entities": self.keyword_extractor(text),
            "summary": self.summarizer(text, max_length=50, min_length=25)[0]['summary_text']
        }

# 优先级队列实现（新增）
class PriorityQueue:
    def __init__(self):
        self._queue = []
        self._count = 0
        self._condition = asyncio.Condition()
        
    async def put(self, item, priority):
        async with self._condition:
            heapq.heappush(self._queue, (-priority, self._count, item))
            self._count += 1
            self._condition.notify()
            
    async def get(self):
        async with self._condition:
            while not self._queue:
                await self._condition.wait()
            return heapq.heappop(self._queue)[-1]
            
    def qsize(self):
        return len(self._queue)


class GBANewsMonitor(YourSpider):
    def __init__(self):
        self.content_analyzer = ContentAnalyzer()  # 新增NLP分析实例
        self.lock = asyncio.Lock()
        self.visited = set()
        self.future_articles = []
        self.crawl_queue = PriorityQueue()  # 替换为优先
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
        # List of user agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
            # Add more user agents as needed
        ]
        self.health_check_task = asyncio.create_task(self.health_check())  # 新增健康检查

    # 新增健康检查方法
    async def health_check(self):
        """健康检查定时任务"""
        while not self.stop_flag:
            await asyncio.sleep(60)
            if self.processed_pages == 0:
                self.logger.warning("检测到爬虫僵死，尝试重启...")
                await self.restart_crawler()
            elif self.crawl_queue.qsize() > 1000:
                self.logger.warning("队列堆积警告，当前队列深度: %d", self.crawl_queue.qsize())


    async def restart_crawler(self):
        """安全重启实现"""
        self.logger.info("执行安全重启...")
        await self.close()
        self.__init__()
        await self.run()

    async def dynamic_render(self, url):
        """改进的动态渲染方法"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy={"server": "per-context"}  # 支持代理
                )
                context = await browser.new_context(
                    user_agent=self.get_random_user_agent(),
                    viewport={'width': 1920, 'height': 1080},
                    java_script_enabled=True
                )
                
                # 智能等待策略
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # 检测加载状态
                if await page.query_selector('text=Loading...'):
                    await page.wait_for_selector('text=Loading...', state='hidden', timeout=30000)
                
                # 滚动加载内容
                scroll_attempts = 0
                last_height = 0
                while scroll_attempts < 3:
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)  # 滚动后等待
                    scroll_attempts += 1
                    last_height = new_height
                
                # 提取最终内容
                content = await page.content()
                await browser.close()
                return content
        except Exception as e:
            self.logger.error(f"动态渲染失败：{url} - {str(e)}")
            return None
    def extract_content_v2(self, html):
        """改进版正文提取"""
        soup = BeautifulSoup(html, 'lxml')
    
        # 第一步：移除广告区块
        for selector in [
            'div.ad', '.ad-box',  # 通用广告
            '.recommend-news',    # 推荐内容
            '.related-news',      # 相关新闻
            '.comment-box'        # 评论区域
        ]:
            for element in soup.select(selector):
                element.decompose()
        
        # 第二步：智能正文定位
        content = None
        for strategy in [
            lambda: self._extract_by_css(soup),
            lambda: self._extract_by_readability(html),
            lambda: self._extract_by_text_density(soup)
        ]:
            content = strategy()
            if content and len(content) > 1000:
                break
        
        # 第三步：内容清洗
        if content:
            # 去除免责声明等
            disclaimer_keywords = ["免责声明", "版权声明", "文章来源"]
            content = '\n'.join([
                p for p in content.split('\n') 
                if not any(kw in p for kw in disclaimer_keywords)
            ])
        
        return content or ""

    def _extract_by_text_density(self, soup):
        """基于文本密度的内容提取"""
        # 计算段落密度
        paragraphs = soup.find_all(['p', 'div'])
        scores = []
        
        for elem in paragraphs:
            text = elem.get_text(strip=True)
            text_length = len(text)
            tag_count = len(elem.find_all())
            density = text_length / (tag_count + 1)  # 避免除以零
            scores.append((elem, density))
        
        # 过滤低密度段落
        avg_density = sum(d for _, d in scores) / len(scores) if scores else 0
        content = [
            elem.get_text(separator='\n', strip=True)
            for elem, density in scores
            if density > avg_density * 0.6
        ]
        
        return '\n'.join(content)

    def _extract_by_css(self, soup):
        """CSS选择器精准提取"""
        content_selectors = [
            ('article', 0.9),         # HTML5文章标签
            ('.article-content', 0.8),
            ('#content', 0.7),
            ('div.content', 0.6),
            ('main', 0.5)
        ]
        
        for selector, min_density in content_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator='\n', strip=True)
                if self._text_density(text) > min_density:
                    return text
        return None

    def _text_density(self, text):
        """文本密度计算"""
        total_length = len(text)
        if total_length == 0:
            return 0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        return chinese_chars / total_length

    def _extract_by_readability(self, html):
        """使用readability算法提取正文内容"""
        try:
            from readability import Document
            doc = Document(html)
            return {
                'content': doc.summary(),
                'title': doc.title()
            }
        except Exception as e:
            self.logger.error(f"Readability提取失败: {str(e)}")
            return None

    def configure(self, keywords, days_range, cities):
        """Configure the monitor with user inputs from web form"""
        self.user_keywords = [kw.strip() for kw in keywords.split(',') if kw.strip()]
        if not self.user_keywords:
            self.user_keywords = CONFIG["content_rules"]["keywords"]
        
        self.expanded_keywords = expand_keywords(self.user_keywords)
        self.days_range = days_range
        # Since cities is already a list, we don't need to split
        self.selected_cities = [city.strip() for city in cities if city.strip() in CONFIG["entry_points"].keys()]
        if not self.selected_cities:
            self.selected_cities = list(CONFIG["entry_points"].keys())
        
        self.filtered_entry_points = {city: CONFIG["entry_points"][city] for city in self.selected_cities}
    async def user_interaction(self, stop_event):
        """Handle user interaction for web environment with stop capability"""
        while not self.stop_flag:
            if stop_event.is_set():
                self.stop_flag = True
                return
            await asyncio.sleep(0.1)  # Check every second or adjust as needed
    async def show_progress(self):
        """Display crawl progress in real-time"""
        while not self.stop_flag:
            print(f"\r[Progress] Processed URLs: {self.processed_pages} | Articles Found: {self.found_articles}", end="", flush=True)
            await asyncio.sleep(CONFIG["ui"]["progress_refresh"])
        print("\n")
    def generate_fingerprint(self, text):
        """Generate content fingerprint for deduplication"""
        features = jieba.cut(text)
        return Simhash(' '.join(features)).value
    async def fetch_page(self, session, url):
        retry_count = 0
        while retry_count < 3:
            try:
                async with session.get(url, timeout=CONFIG["crawl_rules"]["timeout"],
                                    headers={'User-Agent': self.get_random_user_agent()}) as response:
                    if response.status == 200:
                        return await response.text()
                    await self.handle_error_code(response.status, url)
            except Exception as e:
                self.logger.warning(f"Retry {retry_count+1} for {url}: {str(e)}")
                await asyncio.sleep(2 ** retry_count)
                retry_count += 1
        return None
        
    # 新增关闭方法
    async def close(self):
        if hasattr(self, '_browser'):
            await self._browser.close()
            await self._playwright.stop()
        
    def get_random_user_agent(self):
        # Return a random user agent from the list
        return random.choice(self.user_agents)
    async def extract_links(self, html, base_url):
        """智能链接提取"""
        links = await super().extract_links(html, base_url)
        return [link for link in links if self.is_link_worthy(link)]

    def is_link_worthy(self, url):
        """链接价值预测"""
        # 排除常见非内容路径
        exclude_patterns = [
            r'\.(pdf|docx?|xlsx?|ppt|jpg|png)$',
            r'/video/',
            r'/photo/',
            r'/comment/',
            r'/ads?/'
        ]
        if any(re.search(p, url) for p in exclude_patterns):
            return False
            
        # 包含内容路径特征
        include_patterns = [
            r'/article/',
            r'/news/',
            r'_\d+\.html?$',
            r'/content/'
        ]
        return any(re.search(p, url) for p in include_patterns)



    # def parse_content(self, html, url):
    #     """Parse page content, including sentences with future dates"""
    #     soup = BeautifulSoup(html, 'html.parser')
    #     content = self.extract_content_v2(html) 
    #     title = soup.title.string if soup.title else "No Title"
        
    #     # Detect language (very basic, might need a more sophisticated method)
    #     is_cantonese = any(char in content for char in ['係', '哋', '佢', '咗'])
        
    #     # Extract images
    #     images = [img['src'] for img in soup.find_all('img', src=True)[:1]]
        
    #     text_to_search = f"{title} {content}"
        
    #     if len(text_to_search) < CONFIG["content_rules"]["content_validation"]["min_length"]:
    #         return None
    #     # Detect ads or repetitive content
    #     if "广告" in content or "廣告" in content or len(set(content.split())) < 20:
    #         return None
    #     # Extract date, considering both Simplified and Traditional formats
    #     date_match = re.search(r'\b(?:19|20)\d{2}[-\/年]\d{1,2}[-\/月](?:\d{1,2}[日号號])?\b|\b(?:\d{1,2}[日号號月])\b', text_to_search)
    #     if date_match:
    #         pub_date_str = date_match.group()
    #         pub_date_str = pub_date_str.replace('年', '-').replace('月', '-').replace('/', '-').replace('號', '号')
    #         pub_date = self.parse_date(pub_date_str, is_cantonese)
    #     else:
    #         # Log that no date was found
    #         self.logger.info(f"No date found for article at {url}")
    #         pub_date = None  # or set to some default value like datetime.now()
    #     future_sentences = []
    #     sentences = re.split(r'[。？！]', content)
    #     for sentence in sentences:
    #         if self.detect_future_dates({'content': sentence, 'pub_date': pub_date}, is_cantonese):
    #             future_sentences.append(sentence.strip())
    #             break
    #     return {
    #         "title": title,
    #         "content": content,
    #         "pub_date": pub_date,
    #         "url": url,
    #         "images": images,
    #         "future_sentences": future_sentences[:1]
    #     }
    def parse_date(self, date_str, is_cantonese=False):
        """Parse date string, considering the language context"""
        date_pattern = re.compile(r'''
        (?P<year>(?:19|20)\d{2})[年/-]?
        (?P<month>1[0-2]|0?[1-9])[月/-]?
        (?P<day>[12][0-9]|3[01]|0?[1-9])?[日号]?
        ''', re.VERBOSE)
        
        match = date_pattern.search(date_str)
        if match:
            try:
                return datetime(
                    year=int(match.group('year')),
                    month=int(match.group('month')),
                    day=int(match.group('day') or 1)
                )
            except:
                pass
        settings = {'PREFER_DAY_OF_MONTH': 'first', 'RELATIVE_BASE': datetime.now()}
        languages = ['zh'] if not is_cantonese else ['zh-HK', 'zh-TW']
        parsed_date = dateparser.parse(date_str, settings=settings, languages=languages)
        return parsed_date if parsed_date else None
    def detect_future_dates(self, article, is_cantonese=False):
        """增强型未来事件检测（规则+AI）"""
        if not article['pub_date']:
            return False

        future_dates = []
        base_date = article['pub_date']
        content_lower = article['content'].lower()

        # 原有规则检测逻辑
        for key, synonyms in FUTURE_DATE_SYNONYMS.items():
            for synonym in synonyms:
                if synonym in content_lower:
                    # 各时间模式处理逻辑保持不变...
                    if '下月' in key:
                        future_dates.append(base_date + timedelta(days=30))
                    elif '下周' in key:
                        future_dates.append(base_date + timedelta(days=7))
                    # ...其他条件分支保持不变...

        # 绝对日期正则检测
        date_patterns = r'\b(?:19|20)\d{2}[-\/年]\d{1,2}[-\/月](?:\d{1,2}[日号號])?\b|\b(?:\d{1,2}[日号號月])\b'
        absolute_dates = re.findall(date_patterns, article['content'])
        for d in absolute_dates:
            dt = dateparser.parse(d, languages=['zh'])
            if dt and dt > datetime.now() + timedelta(days=CONFIG["content_rules"]["future_days_threshold"]):
                future_dates.append(dt)

        # 新增AI预测（与规则检测结果取或）
        ai_detected = self.ai_predict_future_event(article['content'])
        
        # 任一检测方式命中即返回True
        return len(future_dates) > 0 or ai_detected


    def ai_predict_future_event(self, text):
        """使用NLP模型预测未来事件"""
        classifier = pipeline("text-classification", model="uer/roberta-base-finetuned-chinanews-chinese")
        result = classifier(text[:512])  # 处理前512个字符
        return any(r['label'] == 'future_event' and r['score'] > 0.7 for r in result)

    async def process_page(self, session, url, depth):
        """Process a single page with enhanced error handling and performance optimization"""
        async with self.semaphore:
            try:
                # 第一阶段：快速内容检测
                if not await self.quick_content_check(session, url):
                    self.logger.info(f"内容不符合要求，跳过处理: {url}")
                    return

                # 第二阶段：完整内容处理
                html = await self.acquire_content(session, url)
                if not html:
                    return

                article = self.parse_content_v2(html, url)
                if not article or not self.validate_article(article):
                    return

                # 第三阶段：深度内容分析
                if not self.should_process_article(article):
                    self.logger.info(f"深度过滤排除文章: {url}")
                    return

                # 第四阶段：保存合格内容
                self.save_article(article)
                
                # 第五阶段：智能链接发现
                if depth < CONFIG["crawl_rules"]["max_depth"] - 1:
                    links = await self.extract_links(html, url)
                    self.enqueue_links(links, depth + 1)

            except Exception as e:
                self.logger.error(f"处理异常: {url} - {str(e)}")

    async def quick_content_check(self, session, url):
        """快速内容检测（避免加载完整页面）"""
        try:
            # 使用HEAD请求快速检测
            async with session.head(url, timeout=10, 
                                  headers={'User-Agent': self.get_random_user_agent()}) as resp:
                # 检查Content-Type
                content_type = resp.headers.get('Content-Type', '')
                if 'text/html' not in content_type:
                    self.logger.debug(f"非HTML内容跳过: {url}")
                    return False

            # 获取部分内容检测
            async with session.get(url, timeout=15, 
                                 headers={'Range': 'bytes=0-5000',  # 获取前5KB内容
                                         'User-Agent': self.get_random_user_agent()}) as resp:
                if resp.status not in (200, 206):
                    return False

                chunk = await resp.text()
                return self.is_content_relevant(chunk)

        except Exception as e:
            self.logger.debug(f"快速检测失败: {url} - {str(e)}")
            return True  # 出错时继续处理
        

    def is_content_relevant(self, partial_html):
        """基于部分内容的快速过滤"""
        # 关键词快速匹配
        text = BeautifulSoup(partial_html, 'lxml').get_text()
        keyword_match = any(
            re.search(kw, text, re.IGNORECASE) 
            for kw in self.expanded_keywords
        )
        
        # 日期快速检测
        date_match = re.search(r'\b(?:19|20)\d{2}[-\/年]', text)
        
        # 正文长度预估
        text_length = len(text)
        
        return keyword_match and date_match and text_length > 1000


    def should_process_article(self, article):
        """增强型内容过滤逻辑"""
        # 基础过滤
        if not all([article['title'], article['content']]):
            return False
            
        # 关键词深度匹配（使用TF-IDF算法）
        content = f"{article['title']} {article['content']}".lower()
        keyword_scores = {kw: content.count(kw) for kw in self.expanded_keywords}
        total_score = sum(keyword_scores.values())
        
        # 时间有效性验证
        date_valid = self.is_within_days_range(article['pub_date'])
        
        # 未来事件检测增强
        future_event = self.detect_future_dates(article)
        
        # 综合评分
        return (
            total_score >= 3 and 
            date_valid and 
            (future_event or total_score >= 5)
        )


    def acquire_content(self, session, final_url):
        """智能内容获取策略"""
        if CONFIG["crawl_rules"]["dynamic_render"]:
            return self.dynamic_render(final_url)
        return self.fetch_static_content(session, final_url)

    async def fetch_static_content(self, session, url):
        """带重试机制的静态内容获取"""
        try:
            async with session.get(url, timeout=15) as resp:
                content = await resp.read()
                
                # 优先使用HTTP头信息
                encoding = resp.charset or 'utf-8'
                
                # 备选方案：检测HTML meta标签
                if not encoding:
                    meta_encoding = re.search(r'<meta.*?charset=["\']?([\w-]+)', content.decode('utf-8', errors='ignore'))
                    encoding = meta_encoding.group(1) if meta_encoding else 'utf-8'
                
                # 最终兜底方案
                try:
                    return content.decode(encoding)
                except:
                    return content.decode('gb18030', errors='replace')
                    
        except Exception as e:
            self.logger.warning(f"Static fetch failed: {url} - {str(e)}")
            return None

    def should_process_article(self, article):
        """智能内容过滤逻辑"""
        date_valid = self.is_within_days_range(article['pub_date'])
        future_event = self.detect_future_dates(article)
        keyword_match = any(
            kw in article['title'].lower() or kw in article['content'].lower()
            for kw in self.expanded_keywords
        )
        return date_valid and future_event and keyword_match

    def enqueue_links(self, links, new_depth):
        """智能链接入队策略"""
        batch_size = CONFIG["crawl_rules"]["max_pages"] // (new_depth + 1)
        for link in links[:batch_size]:
            with threading.Lock():  # BloomFilter线程安全
                if not self.url_filter.add(link):
                    continue
            asyncio.create_task(self.crawl_queue.put((link, new_depth)))

    def is_list_page(self, url):
        """新增目录页检测"""
        list_patterns = [
            r'/\d+/$', r'/list/', r'/page/', 
            r'\.html#p=\d+', r'/category/'
        ]
        return any(re.search(p, url) for p in list_patterns)
    
    async def crawl_site(self, session, base_url):
        """改进后的分页爬取方法"""
        page_num = 1
        while self.processed_pages < CONFIG["crawl_rules"]["max_pages"]:
            # 智能分页URL生成
            if 'page=' in base_url:
                url = re.sub(r'page=\d+', f'page={page_num}', base_url)
            else:
                parsed = urlparse(base_url)
                query = parse_qs(parsed.query)
                query['page'] = [str(page_num)]
                url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

            html = await self.fetch_page(session, url)
            if not html:
                break

            # 智能反爬检测与处理
            if any(p in html for p in ["访问过于频繁", "验证码", "Security Verification"]):
                self.logger.warning(f"触发反爬机制：{url}")
                await asyncio.sleep(30)
                continue

            # 内容有效性验证
            if not self.validate_page(html, url):
                self.logger.info(f"终止分页于：{url}")
                break

            # 处理当前页内容
            await self.process_page(session, url, 0)
            self.processed_pages += 1  # 确保计数
            page_num += 1

            # 智能分页终止检测
            if "没有更多内容" in html or page_num > 50:
                break


    def validate_page(self, html, url):
        """智能页面有效性验证"""
        # 基础验证
        if not html or len(html) < 512:
            self.logger.debug(f"内容过短：{url}")
            return False
        
        # 广告页面检测
        ad_keywords = ["广告", "推广", "sponsor", "advertisement"]
        if any(kw in html[:2000] for kw in ad_keywords):
            self.logger.debug(f"广告页面：{url}")
            return False
        
        # 反爬检测增强
        anti_spider_patterns = [
            r"<meta.+__phantomas",
            r"window.location.href\s*=",
            r"请完成安全验证"
        ]
        if any(re.search(p, html) for p in anti_spider_patterns):
            self.logger.warning(f"反爬页面：{url}")
            return False
        
        # 内容结构验证
        content = self.extract_content_v2(html)
        if len(content) < CONFIG["content_rules"]["content_validation"]["min_length"]:
            self.logger.debug(f"内容不足：{url} ({len(content)} chars)")
            return False
        
        return True

    def is_within_days_range(self, pub_date):
        """Check if the publication date is within the user-specified range"""
        if pub_date is None:
            return False  # or handle this case differently if needed
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
                    "pub_date": article['pub_date'].isoformat() if article['pub_date'] else "Unknown"
                },
                "content": article['content'],
                "nlp_analysis": article.get("nlp_analysis", {})
            }, f, ensure_ascii=False)
    def log_operation(self, log_entry):
        """Log operations"""
        with open(CONFIG["storage"]["log_file"], 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    async def task_dispatcher(self, session):
        tasks = []
        sem = asyncio.Semaphore(CONFIG["crawl_rules"]["max_concurrency"])
    
        async def limited_task(url):
            async with sem:
                return await self.crawl_site(session, url['url'])
        
        for city, urls in self.filtered_entry_points.items():
            tasks.extend([limited_task(url) for url in urls])
        
        await asyncio.gather(*tasks)
    def generate_report(self):
        """Generate a report after crawling including an HTML file with future articles and sentences."""
        # 新增链接质量分析
        valid_links = sum(1 for a in self.future_articles 
                        if not self.is_list_page(a['url']) 
                        and len(a['content']) > CONFIG["content_rules"]["content_validation"]["min_length"])
        
        report_content = f"""
        <h3>链接质量分析</h3>
        <p>有效内容页链接：{valid_links}/{len(self.future_articles)}</p>
        <p>疑似目录页链接示例：{
            next((a['url'] for a in self.future_articles if self.is_list_page(a['url'])), '无')
        }</p>
        """
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
                                {{ article.pub_date.strftime('%Y-%m-%d %H:%M') if article.pub_date else "未知" }}
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
    async def run(self, stop_event):
        """Main run function with stop capability"""
        try:
            async with aiohttp.ClientSession() as session:
                self.stop_flag = False
                # Use asyncio.gather to run tasks concurrently
                await asyncio.gather(
                    self.task_dispatcher(session),
                    self.user_interaction(stop_event),
                    self.show_progress()
                )
        except asyncio.CancelledError:
            self.logger.warning("Crawler was forcibly stopped.")
        finally:
            # Ensure report generation and logging occur regardless of how the function exits
            self.generate_report()
            self.logger.info(f"\nProcessed {self.processed_pages} pages and found {self.found_articles} articles.")