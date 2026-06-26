"""
search_tool.py — 多引擎搜索爬虫核心模块
支持百度、Bing(国内版)、搜狗，统一返回 {title, url, snippet} 格式。

Bing 反爬较严，建议安装 curl_cffi 以获得最佳效果：
    pip install curl_cffi

可通过 `search_all(query)` 一键并发搜索；也可直接 `import search_tool` 调用单个引擎。
"""

from __future__ import annotations

import re
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# 统一结果
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""

    def __repr__(self) -> str:
        return f"SearchResult(title={self.title!r}, url={self.url!r})"


# ---------------------------------------------------------------------------
# 公共请求头池
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

_BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}


def _random_ua() -> str:
    return random.choice(_USER_AGENTS)


# ---------------------------------------------------------------------------
# curl_cffi 导入（可选，Bing 需要）
# ---------------------------------------------------------------------------

_curl_cffi_available = False
try:
    from curl_cffi import requests as cffi_requests  # noqa: F811

    _curl_cffi_available = True
except ImportError:
    cffi_requests = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 抽象搜索引擎
# ---------------------------------------------------------------------------


class SearchEngine(ABC):
    """搜索引擎基类 — 子类实现 _build_url / _fetch / _parse_results。"""

    name: str = "base"

    @abstractmethod
    def _build_url(self, query: str) -> str: ...

    @abstractmethod
    def _parse_results(self, soup: BeautifulSoup) -> list[SearchResult]: ...

    def _headers(self) -> dict[str, str]:
        return {**_BASE_HEADERS, "User-Agent": _random_ua()}

    def _fetch(self, url: str, timeout: int) -> requests.Response | None:
        """发送 HTTP 请求，子类可覆盖以使用不同的客户端。"""
        try:
            resp = requests.get(url, headers=self._headers(), timeout=timeout)
            resp.raise_for_status()
            if _is_challenge(resp.text):
                print(f"[{self.name}] 触发验证码/挑战页面，请稍后再试或安装 curl_cffi")
                return None
            return resp
        except requests.RequestException as exc:
            print(f"[{self.name}] 请求失败: {exc}")
            return None

    # ---- 公共接口 ----

    def search(self, query: str, count: int = 10, timeout: int = 15) -> list[SearchResult]:
        url = self._build_url(query)
        resp = self._fetch(url, timeout)
        if resp is None:
            return []

        # 设置编码（curl_cffi 响应无 apparent_encoding 属性）
        if hasattr(resp, "apparent_encoding"):
            resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse_results(soup)[:count]

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# 反爬检测
# ---------------------------------------------------------------------------


def _is_challenge(html: str) -> bool:
    """检测返回页是否为验证码/挑战页面（百度 / Bing / Cloudflare 等）。"""
    lower = html.lower()
    return any(
        keyword in lower
        for keyword in [
            # 百度安全验证
            "百度安全验证",
            "网络不给力，请稍后重试",
            # Bing 挑战页
            "请解决以下难题",
            "verify you are human",
            # Cloudflare / 通用
            "cf-browser-verify",
            "attention required",
            "please turn javascript on",
        ]
    )


# ---------------------------------------------------------------------------
# 百度搜索
# ---------------------------------------------------------------------------


class BaiduSearch(SearchEngine):
    name = "baidu"

    def _build_url(self, query: str) -> str:
        return f"https://www.baidu.com/s?wd={requests.utils.quote(query)}&rn=20"

    def _headers(self) -> dict[str, str]:
        h = super()._headers()
        h["Referer"] = "https://www.baidu.com/"
        return h

    def _fetch(self, url: str, timeout: int) -> requests.Response | None:
        # 百度可能触发安全验证，curl_cffi 可降低概率
        if _curl_cffi_available:
            try:
                resp = cffi_requests.get(  # type: ignore[union-attr]
                    url,
                    impersonate="chrome120",
                    timeout=timeout,
                )
                if resp.status_code == 200 and not _is_challenge(resp.text):
                    return resp  # type: ignore[return-value]
            except Exception:
                pass
        return super()._fetch(url, timeout)

    def _parse_results(self, soup: BeautifulSoup) -> list[SearchResult]:
        results: list[SearchResult] = []

        # 容器选择：新版 div.c-container / div.result，旧版 div[tpl]
        containers = soup.select("div.c-container, div.result-molecule")
        if not containers:
            containers = soup.select("div[tpl]")

        for div in containers:
            if self._is_ad(div):
                continue

            # 标题链接
            title_el = div.select_one("h3.t a, h3.c-title a, h3 a")
            if not title_el:
                continue

            title = self._clean_text(title_el.get_text())
            url = title_el.get("href", "")
            if not title or not url:
                continue

            # 摘要 — div.c-abstract 是最稳定的选择器
            snippet_el = div.select_one(
                "div.c-abstract, "
                "span.content-right_8Zs40, "
                "span.c-span-last, "
                ".c-row"
            )
            snippet = self._clean_text(snippet_el.get_text()) if snippet_el else ""

            results.append(SearchResult(title=title, url=url, snippet=snippet))

        return results

    @staticmethod
    def _is_ad(div: BeautifulSoup) -> bool:
        classes = " ".join(div.get("class", []))
        return "result-op" in classes or "ec_ad" in classes


# ---------------------------------------------------------------------------
# Bing 搜索 (国内版)
# ---------------------------------------------------------------------------


class BingSearch(SearchEngine):
    name = "bing"

    def _build_url(self, query: str) -> str:
        q = requests.utils.quote(query)
        return f"https://www.bing.com/search?q={q}&count=20&setmkt=zh-CN"

    def _fetch(self, url: str, timeout: int) -> requests.Response | None:
        # 优先使用 curl_cffi（Chrome TLS 指纹），可绕过 Bing 的 bot 检测
        if _curl_cffi_available:
            try:
                resp = cffi_requests.get(  # type: ignore[union-attr]
                    url,
                    impersonate="chrome120",
                    timeout=timeout,
                )
                if resp.status_code == 200 and not _is_challenge(resp.text):
                    return resp  # type: ignore[return-value]
                if _is_challenge(resp.text):
                    print(f"[{self.name}] 触发验证码/挑战页面，请稍后再试")
                    return None
            except Exception as exc:
                print(f"[{self.name}] curl_cffi 请求失败: {exc}")
        else:
            print(
                "[bing] 提示: 安装 curl_cffi 可绕过 Bing 反爬检测 → "
                "pip install curl_cffi"
            )

        return super()._fetch(url, timeout)

    def _parse_results(self, soup: BeautifulSoup) -> list[SearchResult]:
        results: list[SearchResult] = []

        items = soup.select("li.b_algo")
        for li in items:
            title_el = li.select_one("h2 a")
            if not title_el:
                continue

            title = self._clean_text(title_el.get_text())
            url = title_el.get("href", "")
            if not title or not url:
                continue

            snippet_el = li.select_one(
                "p.b_lineclamp2, " "p.b_algoSlug, " ".b_caption p, " "p"
            )
            snippet = self._clean_text(snippet_el.get_text()) if snippet_el else ""

            results.append(SearchResult(title=title, url=url, snippet=snippet))

        return results


# ---------------------------------------------------------------------------
# 搜狗搜索
# ---------------------------------------------------------------------------


class SogouSearch(SearchEngine):
    name = "sogou"

    def _build_url(self, query: str) -> str:
        return f"https://www.sogou.com/web?query={requests.utils.quote(query)}"

    def _headers(self) -> dict[str, str]:
        h = super()._headers()
        h["Referer"] = "https://www.sogou.com/"
        return h

    def _parse_results(self, soup: BeautifulSoup) -> list[SearchResult]:
        results: list[SearchResult] = []

        # 新版 div.rb，旧版 div.vrwrap
        items = soup.select("div.vrwrap, div.rb")
        for div in items:
            title_el = div.select_one("h3 a, .vrTitle a, .pt a")
            if not title_el:
                continue

            title = self._clean_text(title_el.get_text())
            url = title_el.get("href", "")
            if not title or not url:
                continue

            snippet_el = div.select_one(
                "div.ft, " "div.space-txt, " "p.star-wiki, " ".str_info_div, " "p"
            )
            snippet = self._clean_text(snippet_el.get_text()) if snippet_el else ""

            results.append(SearchResult(title=title, url=url, snippet=snippet))

        return results


# ---------------------------------------------------------------------------
# 多引擎聚合
# ---------------------------------------------------------------------------

ENGINES: dict[str, SearchEngine] = {
    "baidu": BaiduSearch(),
    "bing": BingSearch(),
    "sogou": SogouSearch(),
}


def search_all(
    query: str,
    engines: list[str] | None = None,
    count: int = 10,
    *,
    progress: Callable[[str], None] | None = print,
) -> dict[str, list[SearchResult]]:
    """串行调用多个引擎，返回 `{引擎名: [结果列表]}`。

    Args:
        query: 搜索关键词。
        engines: 引擎名列表，默认全部 (baidu / bing / sogou)。
        count: 每个引擎最多返回条数。
        progress: 进度回调，传 None 关闭打印。
    """
    if engines is None:
        engines = list(ENGINES.keys())

    all_results: dict[str, list[SearchResult]] = {}

    for name in engines:
        engine = ENGINES.get(name)
        if engine is None:
            if progress:
                progress(f"[skip] 未知引擎: {name}")
            continue

        if progress:
            progress(f"[{name}] 正在搜索: {query}")

        results = engine.search(query, count=count)
        all_results[name] = results

        if progress:
            progress(f"[{name}] 返回 {len(results)} 条结果")

        time.sleep(random.uniform(0.8, 1.5))

    return all_results


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def search_baidu(query: str, count: int = 10) -> list[SearchResult]:
    return BaiduSearch().search(query, count)


def search_bing(query: str, count: int = 10) -> list[SearchResult]:
    return BingSearch().search(query, count)


def search_sogou(query: str, count: int = 10) -> list[SearchResult]:
    return SogouSearch().search(query, count)


# ---------------------------------------------------------------------------
# SearchTool — 自动轮换引擎 & 请求头的高层封装
# ---------------------------------------------------------------------------


class SearchTool:
    """聚合搜索工具 — 自动轮换引擎 / User-Agent，降低单引擎封禁风险。

    用法:
        tool = SearchTool()
        text = tool.web_search("Python 教程")
        print(text)

        # JSON 输出
        json_str = tool.search_json("机器学习", max_results=5)
    """

    def __init__(
        self,
        engines: list[str] | None = None,
        *,
        verbose: bool = False,
    ) -> None:
        """初始化。

        Args:
            engines: 引擎名列表，默认 ["bing", "sogou", "baidu"]。
            verbose: 打印内部日志（引擎切换 / 重试等）。
        """
        self._engines: list[SearchEngine] = [
            ENGINES[name]
            for name in (engines or ["bing", "sogou", "baidu"])
            if name in ENGINES
        ]
        if not self._engines:
            raise ValueError("至少需要一个有效引擎 (baidu / bing / sogou)")

        self._last_engine: str | None = None
        self._cooldown: dict[str, float] = {}  # engine name → 冷却结束时间戳
        self._verbose = verbose
        self._call_count = 0

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def web_search(self, query: str, max_results: int = 5) -> str:
        """搜索并返回格式化文本。

        Args:
            query: 搜索关键词。
            max_results: 最多返回条数 (1~20)。

        Returns:
            人类可读的多行文本，含标题 / 链接 / 摘要。
        """
        results: list[SearchResult] = []
        engine_used = self._do_search(query, max_results, results)
        print(results)
        return self._format_text(query, results, engine_used)

    def search_json(self, query: str, max_results: int = 5) -> str:
        """搜索并返回 JSON 字符串。

        Returns:
            JSON 数组，每项 {"title", "url", "snippet", "engine"}。
        """
        import json as _json

        results: list[SearchResult] = []
        engine_used = self._do_search(query, max_results, results)

        payload = [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "engine": engine_used,
            }
            for r in results
        ]
        return _json.dumps(payload, ensure_ascii=False, indent=2)
    
    def do_search(
        self, query: str, max_results: int, out: list[SearchResult]
    ) -> str:
        return self._do_search(query,max_results,out)
    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _do_search(
        self, query: str, max_results: int, out: list[SearchResult]
    ) -> str:
        """核心搜索流程：轮换引擎直到成功，结果写入 out。返回实际使用的引擎名。"""
        max_results = max(1, min(max_results, 20))
        attempted: set[str] = set()

        for _ in range(len(self._engines)):
            engine = self._pick_engine()
            if engine.name in attempted:
                continue
            attempted.add(engine.name)

            # 冷却检查
            now = time.time()
            if now < self._cooldown.get(engine.name, 0):
                if self._verbose:
                    print(f"[SearchTool] {engine.name} 冷却中，跳过")
                continue

            if self._verbose:
                print(f"[SearchTool] 使用引擎: {engine.name}")

            try:
                results = engine.search(query, count=max_results, timeout=20)
                if results:
                    out.extend(results)
                    self._last_engine = engine.name
                    self._call_count += 1
                    return engine.name
                # 返回空列表也视为失败（可能被屏蔽）
                self._set_cooldown(engine.name, 120)
            except Exception as exc:
                if self._verbose:
                    print(f"[SearchTool] {engine.name} 异常: {exc}")
                self._set_cooldown(engine.name, 300)

        # 全部失败
        out.clear()
        return "none"

    def _pick_engine(self) -> SearchEngine:
        """随机选取引擎（避免与上次重复，优先未冷却引擎）。"""
        now = time.time()
        # 权重：未冷却 > 冷却中；非上次使用 +1
        def _weight(eng: SearchEngine) -> float:
            w = 1.0
            if now < self._cooldown.get(eng.name, 0):
                w *= 0.01  # 大幅降低冷却引擎权重
            if eng.name == self._last_engine:
                w *= 0.3  # 降低重复概率
            return w

        weights = [_weight(e) for e in self._engines]
        total = sum(weights)
        if total <= 0:
            return random.choice(self._engines)

        r = random.uniform(0, total)
        cumulative = 0.0
        for eng, w in zip(self._engines, weights):
            cumulative += w
            if r <= cumulative:
                return eng
        return self._engines[-1]

    def _set_cooldown(self, name: str, seconds: float) -> None:
        self._cooldown[name] = time.time() + seconds
        if self._verbose:
            print(f"[SearchTool] {name} 进入冷却 {seconds}s")

    @staticmethod
    def _format_text(
        query: str, results: list[SearchResult], engine: str
    ) -> str:
        """格式化为人类可读文本。"""
        import textwrap as _tw

        if not results:
            return f"搜索 \"{query}\" 无结果（所有引擎均未返回数据）。"

        lines = [
            f"搜索: {query}",
            f"引擎: {engine}  共 {len(results)} 条结果",
            "─" * 50,
        ]
        for i, r in enumerate(results, 1):
            title = r.title
            url = r.url
            snippet = _tw.shorten(r.snippet, width=200, placeholder="…")

            lines.append(f"\n{i}. {title}")
            lines.append(f"   {url}")
            if snippet:
                lines.append(f"   {snippet}")

        return "\n".join(lines)
