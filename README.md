# 🎮 AstrBot MC 服务器监控面板插件

一个基于 AstrBot 的 Minecraft 服务器状态查询插件，支持多服务器并发查询、彩色 MOTD 解析、API 故障转移，并**在本地使用 Pillow 渲染**出具有毛玻璃风格的监控面板大图（不依赖任何外部文转图 / t2i 服务）。

## ✨ 功能特性

- **多服务器监控**：一次 `/mc` 指令即可查询所有已配置的服务器，自动生成监控面板。
- **本地渲染出图**：所有图片由 Pillow 在插件进程内直接绘制，无外部渲染服务依赖，断网也能画图（只是数据查不到）。
- **API 故障转移机制**：内置多个查询 API（MineBBS、mcstatus.io、mcsrvstat.us），支持自定义 API 优先级。主 API 失败时自动降级尝试下一个，保证查询成功率。
- **毛玻璃视觉风格**：深色/浅色渐变背景，卡片支持使用服务器图标作为模糊背景，观感接近现代化监控面板。
- **彩色 MOTD 支持**：完整解析 Minecraft 原版 `§` 颜色代码以及 JSON 聊天组件，还原游戏内彩色 MOTD。
- **高度可配置**：在 Web UI 中可自由调整图片宽度、字体大小、主题模式，并独立控制是否显示玩家数、版本、延迟、MOTD。
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

在 AstrBot Web UI 的插件配置页中，可以配置以下选项：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `servers` | 服务器地址列表，**多个地址用英文逗号分隔** | `mc.example.com, be.example.com:19132` |
| `brand_name` | 卡片左上角显示的品牌名称 | `无名小服` |
| `api_priority` | API 优先级（失败自动切换下一个）。内置：`minebbs` / `mcstatus` / `mcsrvstat`，也可填入自定义 URL（需带 `{ip}` 和 `{port}` 占位符），多个用英文逗号分隔 | `minebbs,mcstatus,mcsrvstat` |
| `query_timeout` | 单次 API 查询超时时间（秒） | `10` |
| `default_port` | 默认端口（Java 版 25565，基岩版 19132） | `25565` |
| `theme` | 主题模式：`auto` / `light` / `dark` | `dark` |
| `card_width` | 图片宽度（像素） | `900` |
| `font_size` | 基础字体大小 | `28` |
| `show_motd` | 是否显示 MOTD | `true` |
| `show_players` | 是否显示在线/最大玩家数 | `true` |
| `show_version` | 是否显示版本信息 | `true` |
| `show_delay` | 是否显示延迟 | `true` |

> 💡 关闭任意 `show_*` 开关后，卡片会自动收缩对应格子，布局不会留下空白。

## 🕹️ 使用方法

- **查询已配置的所有服务器**：

  ```text
  /mc
  ```

  插件会读取 `servers` 中的列表，并发查询并渲染监控面板。

- **查询单个指定服务器**（不受 `servers` 列表限制）：

  ```text
  /mc mc.example.com
  /mc mc.example.com:25565
  /mc be.example.com:19132
  ```

- **防抖**：3 秒内重复发送 `/mc` 会被忽略，避免刷屏和刷 API。

## 📝 自定义 API 说明

如果 `api_priority` 中填的值既不是 `minebbs` / `mcstatus` / `mcsrvstat`，插件会把它当作完整 URL，并用 `{ip}`、`{port}` 做占位符替换。例如：

```text
minebbs,https://your-api.com/query?ip={ip}&port={port}
```

插件会按顺序尝试：先 `minebbs`，失败再请求你的自定义 API。返回 JSON 建议尽量兼容以下字段（能识别多少就用多少）：

```json
{
  "motd": "服务器标语",
  "players": { "online": 3, "max": 20 },
  "version": "1.20.4",
  "delay": 42,
  "favicon": "data:image/png;base64,...."
}
```

## 🎨 关于渲染

- 所有图片均由插件内的 Pillow 绘制，**不会调用 AstrBot 的 t2i 服务**，也不依赖任何远程图片渲染端点。
- 渲染结果会先写入 `/tmp/astrbot_mc_motd/`，再由 AstrBot 作为图片消息发送。临时文件超过 1 小时会自动清理。
- 如果希望在图片中使用自定义字体，把 `font.ttf` / `font.ttc` / `font.otf` 放到插件目录即可，插件会优先加载。

## 🌐 网络依赖提示

插件的**出图能力完全离线**，但**查询数据仍需要联网**访问以下公共 API（任选其一可用即可）：

- `https://motd.minebbs.com`
- `https://api.mcstatus.io`
- `https://api.mcsrvstat.us`

若服务器在国内且访问这些地址超时，请为 AstrBot 容器配置 HTTP/HTTPS 代理，例如：

```bash
HTTP_PROXY=http://宿主机IP:7890
HTTPS_PROXY=http://宿主机IP:7890
NO_PROXY=localhost,127.0.0.1,192.168.0.0/16
```

> Docker 环境中不要写 `127.0.0.1:7890`，那指向容器自身，应使用宿主机 IP 或代理服务名。

## 📄 开源协议

本项目采用 MIT 协议开源。
