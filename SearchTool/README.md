# SearchTool — 多引擎搜索器

基于 Python 的简易搜索引擎爬虫，支持 **百度 / Bing(国内版) / 搜狗**。

## 安装

```bash
pip install -r requirements.txt
```

> **注意**：`curl_cffi` 用于模拟 Chrome TLS 指纹，可有效绕过百度和 Bing 的反爬检测。若安装失败（需编译环境），百度/Bing 仍可回退到标准 `requests`，但成功率会降低。

## 命令行使用

```bash
# 单引擎搜索
python main.py -e baidu -q "Python 教程"

# 多引擎同时搜索
python main.py -e baidu,bing,sogou -q "机器学习"

# 限制返回条数
python main.py -e bing -q "docker compose" -n 5

# 默认全部引擎
python main.py -q "fastapi 入门"
```

## Python 模块调用

```python
from search_tool import search_all, search_baidu, search_bing, search_sogou

# 单引擎
results = search_bing("Python 教程", count=5)
for r in results:
    print(r.title, r.url, r.snippet)

# 多引擎聚合
all_results = search_all("机器学习", engines=["baidu", "bing"], count=10)
for engine, results in all_results.items():
    print(f"\n[{engine}] {len(results)} 条结果")
    for r in results[:3]:
        print(f"  {r.title}")
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `search_tool.py` | 核心爬虫模块（引擎实现 + 聚合接口） |
| `main.py` | 命令行入口 |
| `requirements.txt` | 依赖清单 |

## 三方引擎适配说明

| 引擎 | 反爬强度 | 推荐方案 |
|------|----------|----------|
| 百度 | 中 | `curl_cffi` + Chrome 指纹 |
| Bing | 高 | 必须 `curl_cffi`（标准 requests 基本不可用） |
| 搜狗 | 低 | 标准 `requests` 即可 |

## 注意事项

- 各引擎有反爬机制，引擎间请求间隔已内置 0.8~1.5s 随机延迟
- 若被临时封禁，稍等几分钟再试
- 搜索结果仅供学习参考，请遵守各搜索引擎的服务条款
