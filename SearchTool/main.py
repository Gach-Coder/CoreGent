"""
main.py — 命令行搜索入口

用法:
    # 自动轮换引擎模式（推荐，防封）
    python main.py --tool -q "Python 教程"

    # JSON 输出
    python main.py --tool --json -q "机器学习" -n 5

    # 传统多引擎模式
    python main.py -e baidu -q "Python 教程"
    python main.py -e baidu,bing,sogou -q "机器学习"
"""

from __future__ import annotations

import argparse
import textwrap

from search_tool import ENGINES, SearchResult, SearchTool, search_all


def _format_table(results: list[SearchResult], engine_name: str) -> str:
    lines: list[str] = []
    header = f"\n{'=' * 70}\n  [{engine_name.upper()}] 共 {len(results)} 条结果\n{'=' * 70}"
    lines.append(header)

    if not results:
        lines.append("  (无结果)")
        return "\n".join(lines)

    for i, r in enumerate(results, 1):
        title = textwrap.shorten(r.title, width=56, placeholder="…")
        url = textwrap.shorten(r.url, width=70, placeholder="…")
        snippet = textwrap.shorten(r.snippet, width=66, placeholder="…")

        lines.append(f"\n  [{i}] {title}")
        lines.append(f"      {url}")
        if snippet:
            lines.append(f"      {snippet}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="多引擎搜索器 — 支持百度 / Bing(国内) / 搜狗",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python main.py --tool -q "Python 教程"          # 自动轮换引擎
              python main.py --tool --json -q "机器学习"      # JSON 输出
              python main.py -e baidu,bing -q "机器学习"      # 传统多引擎
        """),
    )

    parser.add_argument(
        "-e", "--engine",
        default="baidu,bing,sogou",
        help="传统模式: 搜索引擎 (逗号分隔)",
    )
    parser.add_argument(
        "-q", "--query",
        required=True,
        help="搜索关键词",
    )
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=10,
        help="每个引擎返回的最大条数 (默认 10)",
    )
    parser.add_argument(
        "--tool",
        action="store_true",
        help="使用 SearchTool 自动轮换引擎模式（推荐，防封）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 格式输出（需与 --tool 配合）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示引擎切换 / 重试日志",
    )

    args = parser.parse_args()

    if args.tool:
        # ----- SearchTool 模式 -----
        tool = SearchTool(verbose=args.verbose)

        if args.json:
            print(tool.search_json(args.query, max_results=args.count))
        else:
            print(tool.web_search(args.query, max_results=args.count))
        return

    # ----- 传统多引擎模式 -----
    engines = [e.strip() for e in args.engine.split(",") if e.strip()]

    print(f"🔍 正在搜索: {args.query}")
    print(f"📡 引擎: {', '.join(engines)}\n")

    all_results = search_all(args.query, engines=engines, count=args.count)

    for name in engines:
        results = all_results.get(name, [])
        print(_format_table(results, name))

    total = sum(len(v) for v in all_results.values())
    print(f"\n{'─' * 70}")
    print(f"  总计: {total} 条结果 ({len(all_results)} 个引擎)")
    print(f"{'─' * 70}\n")


if __name__ == "__main__":
    main()
