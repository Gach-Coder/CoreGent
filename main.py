"""
入口模块 —— 交互式命令行界面，接收用户输入并交给 Agent 处理。

用法:
    python main.py                     # 交互模式
    python main.py "列出当前目录文件"    # 单次模式

环境变量:
    DEEPSEEK_API_KEY  —— DeepSeek API 密钥（必须）
    DEEPSEEK_MODEL    —— 模型名，默认 deepseek-v4-flash
"""

import sys
from agent import Agent
import config

def print_banner():
    print("=" * 54)
    print("  🤖 CoreGent —— 智能体命令行工具")
    print(f"  模型: {config.MODEL}")
    print(f"  端点: {config.BASE_URL}")
    print("  输入 'help'  查看示例 | 'reset' 重置对话 | 'quit' 退出")
    print("=" * 54)


def show_help():
    print("""
📋 可用命令:
  help      - 显示此帮助
  reset     - 重置对话历史
  quit/exit - 退出程序

💡 示例请求:
  • 列出当前目录下的所有文件
  • 在当前目录创建一个 hello.py，内容是打印 Hello World
  • 运行 python --version 看看 Python 版本
  • 搜索当前目录下所有 .py 文件
""")


def main():
    # 检查 API Key
    if config.API_KEY == "your-api-key-here":
        print("❌ 错误: 请先设置环境变量 DEEPSEEK_API_KEY")
        print("   Windows: set DEEPSEEK_API_KEY=sk-xxxx")
        print("   Linux/Mac: export DEEPSEEK_API_KEY=sk-xxxx")
        sys.exit(1)

    agent = Agent(
        log_path=config.LOG_PATH,
        log_echo=config.LOG_ECHO,
        stream=config.STREAM,
    )

    # ---- 显示 MCP 状态 ----
    try:
        from tools import TOOL_MAP
        mcp_tool_count = sum(
            1 for name in TOOL_MAP
            if name.startswith(config.MCP_TOOL_PREFIX)
        )
        if mcp_tool_count > 0:
            print(f"  [🔌 MCP] {mcp_tool_count} 个 MCP 工具已注册")
    except Exception:
        pass

    # ---- 单次模式 ----
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        print(f"👤 You: {user_input}")
        agent.run(user_input)
        print(f"\n📄 详细日志已写入: {config.LOG_PATH}")
        return

    # ---- 交互模式 ----
    print_banner()
    print(f"📄 日志文件: {config.LOG_PATH}")
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见!")
            break

        if not user_input:
            continue

        lower = user_input.lower()
        if lower in ("quit", "exit", "q"):
            print("👋 再见!")
            break
        if lower == "help":
            show_help()
            continue
        if lower == "reset":
            agent.reset()
            continue

        try:
            agent.run(user_input)
        except Exception as e:
            print(f"\n❌ 运行出错: {e}")
            # 错误也写入日志
            agent.logger.error(str(e))


if __name__ == "__main__":
    main()
