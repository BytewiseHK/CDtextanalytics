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
        "珠海": "https://news.hizh.cn/"
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