# 🎮 AstrBot MC 服务器监控面板插件

一个基于 AstrBot 的 Minecraft 服务器状态查询插件，支持多服务器并发查询、彩色 MOTD 解析、API 故障转移，并生成具有毛玻璃风格的监控面板大图。

> 💡 **本插件由 [DeepSeek](https://www.deepseek.com/) 制作。**

## ✨ 功能特性

- **多服务器监控**：一次 `/mc` 指令即可查询所有已配置的服务器，自动生成监控面板。
- **API 故障转移机制**：内置多个查询 API（MineBBS、mcstatus.io、mcsrvstat.us），支持自定义 API 优先级。当主 API 查询失败时，自动降级尝试下一个 API，保证查询成功率。
- **毛玻璃视觉风格**：采用深色/浅色渐变背景，卡片支持服务器图标作为模糊背景，带来极佳的视觉体验。
- **彩色 MOTD 支持**：完整解析 Minecraft 原版 `§` 颜色代码以及 JSON 聊天组件，还原游戏内彩色 MOTD 效果。
- **高度可配置**：在 Web UI 中可自由调整图片宽度、字体大小、主题模式，以及是否显示玩家数、版本、延迟等数据。
- **智能防抖**：内置异步防抖机制，避免短时间内频繁请求 API。

## 📦 安装方法

1. 将本插件文件夹放入 AstrBot 的 `data/plugins/` 目录下。
2. 确保文件夹内包含以下文件：
   - `main.py`
   - `_conf_schema.json`
   - `metadata.yaml`
   - `requirements.txt`
3. 在 AstrBot 的 Web UI 插件管理页面中，点击“重载插件”即可自动安装依赖并生效。

## ⚙️ 配置说明（Web UI）

插件安装后，在 AstrBot 的 Web UI 插件配置页面中，你可以配置以下选项：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `servers` | 服务器地址列表（英文逗号分隔） | `mc.example.com, be.example.com:19132` |
| `api_priority` | API 优先级列表（失败自动切换下一个）。内置值：`minebbs`, `mcstatus`, `mcsrvstat`。也可填入自定义 API 的 URL（需带 `{ip}` 和 `{port}` 占位符） | `minebbs,mcstatus,mcsrvstat` |
| `query_timeout` | 单次 API 查询超时时间（秒） | `10` |
| `default_port` | 默认端口（Java版 25565，基岩版 19132） | `25565` |
| `auto_detect` | 是否自动检测服务器类型 | `true` |
| `show_motd` | 是否显示 MOTD | `true` |
| `show_players` | 是否显示在线玩家数 | `true` |
| `show_version` | 是否显示版本信息 | `true` |
| `show_delay` | 是否显示延迟 | `true` |
| `card_width` | 图片宽度（像素） | `900` |
| `font_size` | 基础字体大小 | `28` |
| `theme` | 主题模式（`auto` / `light` / `dark`） | `dark` |
| `brand_name` | 顶部显示的服务器品牌名称 | `无名小服` |

## 🕹️ 使用方法

- **查询已配置的所有服务器**：
  ```text
  /mc
插件会自动读取 servers 中的列表，并发查询并渲染监控面板。

查询单个指定服务器：

text
/mc mc.example.com
/mc mc.example.com:25565
/mc be.example.com:19132
📝 自定义 API 说明
如果你想使用自己的 API，可以在 api_priority 中填入完整的 URL，并用 {ip} 和 {port} 作为占位符。例如：

text
minebbs,https://your-api.com/query?ip={ip}&port={port}
插件会按顺序尝试，如果 minebbs 失败，则自动请求你的自定义 API。自定义 API 的返回数据格式需尽量兼容标准字段（motd, players, version, delay, favicon），或参考内置 API 格式进行适配。

📄 开源协议
本项目采用 MIT 协议开源。