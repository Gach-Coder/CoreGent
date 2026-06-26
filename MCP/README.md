# MCP File Server

基于 Python 的 MCP (Model Context Protocol) 文件系统服务器，根目录为 MCP 模块所在目录。

## 提供的工具

| 工具 | 功能 |
|------|------|
| `write_file` | 写入文件内容（自动创建父目录） |
| `read_file` | 读取文件内容 |
| `list_directory` | 列出目录内容 |
| `delete_file` | 删除文件 |
| `get_file_info` | 获取文件元信息 |
| `Pet_Hajimi` | 摸一摸哈基米 |
 
## 安装 & 运行

```bash
pip install -r requirements.txt
python server.py
```

## 配置 MCP 客户端

在客户端的配置文件中添加：

```json
{
    "mcpServers": {
        "filesystem": {
            "command": "python",
            "args": ["MCP/server.py"]
        }
    }
}
```

## 安全

所有路径被限定在根目录 `D:\DATA\PythonProj\MCP` 内，防止目录穿越攻击。
