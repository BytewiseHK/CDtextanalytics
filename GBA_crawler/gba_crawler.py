import re
import json
from datetime import datetime, timedelta
from dateutil.parser import parse
import requests
from bs4 import BeautifulSoup
import jieba
import jieba.posseg as pseg
from googletrans import Translator
from apscheduler.schedulers.background import BackgroundScheduler
import urllib3
import os
from urllib.parse import urljoin

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GBANewsCrawler:
    def __init__(self):
        self.sources = {
            '广州': 'https://news.dayoo.com/guangzhou/',
            '深圳': 'https://www.sznews.com/news/',
            '珠海': 'https://www.hizh.cn/node_1.htm',
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


        }
        self.base_urls = {
            'jmnews.com.cn': 'http://www.jmnews.com.cn',
            'huizhou.cn': 'http://www.huizhou.cn',
            'xjrb.com': 'http://www.xjrb.com'
        }
        self.keywords = ["政策", "峰会", "基建", "GDP", "交通", "发展", "规划", "项目"]
        self.event_triggers = {
            '政务': ["揭牌", "签约", "发布"],
            '经济': ["开工", "投产", "交易额"],
            '民生': ["启用", "调整", "开通"]
        }
        self.visited_urls = set()  # 记录已访问的URL
        self.max_depth = 2  # 递归深度限制
        self.max_pages = 50  # 每个源的最大页面数限制
        self.seen_content = set()  # 用于去重

    def get_base_url(self, url):
        for domain, base in self.base_urls.items():
            if domain in url:
                return base
        return '/'.join(url.split('/')[:3])

    def fetch_news(self, url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            response.encoding = response.apparent_encoding
            print(f"正在抓取: {url}")
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"抓取失败: {str(e)}")
            return None

    def is_valid_url(self, url):
        # 修改日期匹配规则，使其更宽松
        if not url:
            return False
        date_patterns = [
            r'/202[0-9]/\d{2}/',  # 匹配 /2023/01/ 格式
            r'202[0-9]\d{2}',     # 匹配 202301 格式
            r'/content_\d+',       # 匹配 content_123456 格式
            r'/[a-z]+/\d{8}/',    # 匹配 /news/20230101/ 格式
        ]
        return any(re.search(pattern, url) for pattern in date_patterns)

    def contains_keywords(self, text):
        # 添加更多关键词组合
        keyword_groups = {
            '规划发展': ['规划', '发展', '建设', '战略'],
            '经济指标': ['GDP', '增长', '投资', '产业'],
            '重大项目': ['项目', '工程', '基建', '基础设施'],
            '政策方向': ['政策', '措施', '实施', '推进'],
            '民生改善': ['民生', '服务', '改善', '提升']
        }
        
        for group_keywords in keyword_groups.values():
            if any(keyword in text for keyword in group_keywords):
                return True
        return False

    def recursive_crawl(self, url, depth=0):
        if depth >= self.max_depth or url in self.visited_urls:
            return []
        
        self.visited_urls.add(url)
        articles = []
        
        try:
            soup = self.fetch_news(url)
            if not soup:
                return []

            # 获取所有链接
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                if not href:
                    continue

                # 处理相对URL
                if not href.startswith('http'):
                    href = urljoin(url, href)

                # 检查URL是否符合条件
                if self.is_valid_url(href) and href not in self.visited_urls:
                    # 获取文章内容
                    article = self.extract_content(soup, href)
                    if article and self.contains_keywords(article['content']):
                        articles.append(article)
                        
                    # 递归爬取
                    if len(articles) < self.max_pages:
                        articles.extend(self.recursive_crawl(href, depth + 1))

            return articles
        except Exception as e:
            print(f"递归爬取失败 - {url}: {str(e)}")
            return articles

    def is_duplicate_content(self, content):
        # 使用内容的哈希值进行去重
        content_hash = hash(content)
        if content_hash in self.seen_content:
            return True
        self.seen_content.add(content_hash)
        return False

    def extract_content(self, soup, source_url):
        if soup is None:
            return None
            
        try:
            # 通用选择器
            title = None
            content = []
            
            # 尝试多种标题选择器
            title_selectors = [
                'h1',
                '.article-title',
                '.content-title',
                '.news-title',
                '.title'
            ]
            
            for selector in title_selectors:
                title = soup.select_one(selector)
                if title:
                    break
            
            # 尝试多种内容选择器
            content_selectors = [
                '.article-content p',
                '.content p',
                '.news-content p',
                'article p',
                '.text p'
            ]
            
            for selector in content_selectors:
                content = soup.select(selector)
                if content:
                    content_text = '\n'.join([p.text.strip() for p in content if p.text.strip()])
                    break

            if title and content:
                # 检查是否是重复内容
                if self.is_duplicate_content(content_text):
                    return None
                    
                article = {
                    'title': title.text.strip(),
                    'content': content_text,
                    'url': source_url,
                    'publish_date': self.extract_publish_date(soup)
                }
                return article
            
            return None
        except Exception as e:
            print(f"解析失败 - {source_url}")
            return None

    def extract_publish_date(self, soup):
        # 尝试从页面提取发布日期
        date_selectors = [
            '.article-info .date',
            '.time',
            '.publish-time',
            'time',
            '.article-date'
        ]
        for selector in date_selectors:
            date_element = soup.select_one(selector)
            if date_element:
                try:
                    date_text = date_element.text.strip()
                    # 尝试解析日期
                    return parse(date_text, fuzzy=True).strftime('%Y-%m-%d')
                except:
                    continue
        return None

class TemporalAnalyzer:
    def __init__(self):
        self.current_date = datetime.now()
        # 排除的关键词（广告、无关内容等）
        self.exclude_keywords = [
            '广告', '推广', '点击', '详询', '咨询电话',
            '版权所有', '责任编辑', '记者'
        ]

    def clean_content(self, text):
        # 清理广告和无关内容
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            if not any(kw in line for kw in self.exclude_keywords) and len(line.strip()) > 10:
                cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

    def detect_future_dates(self, text):
        # 清理内容
        text = self.clean_content(text)
        
        dates = []
        # 明确的未来日期
        date_patterns = [
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', '%Y年%m月%d日'),
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
            (r'(\d{4})/(\d{1,2})/(\d{1,2})', '%Y/%m/%d')
        ]
        
        # 相对日期表达
        relative_patterns = {
            r'([下后]个?月)': (1, 'month'),
            r'(\d+个月[后内])': ('n', 'month'),
            r'明年': (1, 'year'),
            r'后年': (2, 'year'),
            r'(\d+年[后内])': ('n', 'year'),
            r'([下后]\s*季度)': (1, 'quarter'),
            r'(\d+天[后内])': ('n', 'day')
        }

        # 处理明确的日期
        for pattern, date_format in date_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    date_str = match.group(0)
                    date = datetime.strptime(date_str, date_format)
                    if date > self.current_date:
                        dates.append({
                            'date': date.strftime('%Y-%m-%d'),
                            'original': date_str,
                            'context': text[max(0, match.start()-20):match.end()+20]
                        })
                except:
                    continue

        # 处理相对日期
        for pattern, (offset, unit) in relative_patterns.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    date = self.current_date
                    if offset == 'n':
                        # 提取数字
                        num = int(re.search(r'\d+', match.group(0)).group())
                    else:
                        num = offset
                        
                    if unit == 'month':
                        date = date.replace(month=date.month + num)
                    elif unit == 'year':
                        date = date.replace(year=date.year + num)
                    elif unit == 'quarter':
                        date = date.replace(month=date.month + 3*num)
                    elif unit == 'day':
                        date = date + timedelta(days=num)
                        
                    dates.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'original': match.group(0),
                        'context': text[max(0, match.start()-20):match.end()+20]
                    })
                except:
                    continue

        # 去重并排序
        unique_dates = []
        seen = set()
        for date_info in sorted(dates, key=lambda x: x['date']):
            if date_info['date'] not in seen:
                seen.add(date_info['date'])
                unique_dates.append(date_info)

        return unique_dates if unique_dates else None

class EventDetector:
    def __init__(self):
        self.translator = Translator()
    
    def translate_content(self, text):
        try:
            # 简单的英文摘要，避免翻译问题
            return f"News summary from {datetime.now().strftime('%Y-%m-%d')}"
        except:
            return ""

    def analyze_event(self, text):
        # 使用jieba进行分词和词性标注
        words = pseg.cut(text)
        entities = []
        
        # 实体识别（简化版）
        for word, flag in words:
            if flag.startswith('n'):  # 名词
                entities.append({
                    'text': word,
                    'label': 'NOUN',
                    'start': text.index(word),
                    'end': text.index(word) + len(word)
                })
        
        # 影响力计算
        economic_terms = len([w for w, f in words if w in ['GDP', '投资', '亿元']])
        gov_terms = len([w for w, f in words if f == 'nt'])  # 机构名词
        impact_score = economic_terms*0.4 + gov_terms*0.3
        
        return {
            'impact': impact_score,
            'entities': entities,
            'translated': self.translate_content(text[:500])
        }

class ReportGenerator:
    def __init__(self):
        self.last_content = set()  # 用于存储上次的新闻内容

    def is_new_content(self, news_items):
        # 将当前新闻转换为可哈希的形式用于比较
        current_content = set()
        for item in news_items:
            # 使用标题和内容的组合作为唯一标识
            content_id = f"{item['title']}_{item['dates']}"
            current_content.add(content_id)
        
        # 检查是否有新内容
        is_new = current_content != self.last_content
        # 更新存储的内容
        self.last_content = current_content
        return is_new

    def generate_html(self, news_items):
        html_template = """
        <html>
        <head>
            <title>大湾区新闻简报 {date}</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .event-card {{ 
                    border: 1px solid #ddd; 
                    padding: 15px; 
                    margin: 10px; 
                    border-radius: 5px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .highlight {{ color: #e74c3c; font-weight: bold; }}
                h1, h3 {{ color: #2c3e50; }}
            </style>
        </head>
        <body>
            <h1>粤港澳大湾区每日简报</h1>
            <h3>{date}</h3>
            {content}
        </body>
        </html>
        """
        
        content = []
        for item in news_items:
            content.append(f"""
            <div class="event-card">
                <h2>{item['title']}</h2>
                <p><span class="highlight">发生时间:</span> {', '.join(item['dates'])}</p>
                <p><span class="highlight">影响城市:</span> {item['city']}</p>
                <p>{item['summary']}</p>
                <p>English Summary: {item['translated']}</p>
            </div>
            """)
        
        return html_template.format(
            date=datetime.now().strftime('%Y-%m-%d'),
            content='\n'.join(content)
        )

# 初始化系统组件
crawler = GBANewsCrawler()
analyzer = TemporalAnalyzer()
detector = EventDetector()
generator = ReportGenerator()

def daily_pipeline():
    print("\n=== 开始抓取新闻 ===")
    news_items = []
    
    # 数据采集
    for city, url in crawler.sources.items():
        print(f"\n正在抓取{city}新闻...")
        articles = crawler.recursive_crawl(url)
        
        for article in articles:
            # 先检查是否包含未来时间
            future_dates = analyzer.detect_future_dates(article['content'])
            if future_dates and any(
                datetime.strptime(date_info['date'], '%Y-%m-%d') > datetime.now() 
                for date_info in future_dates
            ):
                analysis = detector.analyze_event(article['content'])
                news_items.append({
                    'city': city,
                    'title': article['title'],
                    'dates': [date_info['date'] for date_info in future_dates],
                    'date_contexts': [date_info['context'] for date_info in future_dates],
                    'summary': analysis['entities'][:3],
                    'translated': analysis['translated'],
                    'impact': analysis['impact'],
                    'url': article['url']
                })
                print(f"发现未来事件新闻：{article['title']}")
    
    if not news_items:
        print("\n未获取到包含未来时间的新闻")
        return
    
    # 检查是否有新内容
    if not generator.is_new_content(news_items):
        print("\n没有新的新闻内容，不生成新报告")
        return
        
    # 生成报告
    try:
        html_report = generator.generate_html(news_items)
        
        # 创建输出目录
        output_dir = f'crawl_results_{datetime.now().strftime("%d%b%Y")}'
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存报告
        report_path = os.path.join(output_dir, f'report_{datetime.now().strftime("%Y%m%d")}.html')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        # 保存原始数据
        data_path = os.path.join(output_dir, 'raw_data.json')
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(news_items, f, ensure_ascii=False, indent=2)
        
        print(f"\n=== 抓取完成 ===")
        print(f"共获取 {len(news_items)} 条新闻")
        print(f"报告已保存至：{output_dir}/")
    except Exception as e:
        print(f"\n保存文件时发生错误: {str(e)}")

# 定时任务配置
scheduler = BackgroundScheduler()
scheduler.add_job(daily_pipeline, 'cron', hour=8)
scheduler.start()

if __name__ == "__main__":
    daily_pipeline()