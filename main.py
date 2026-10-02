from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

import io
import os
import re
import time
import uuid
import json
import asyncio
import base64
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageColor

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None

# ============ 防抖装饰器 ============
def _debounce(wait=2.0):
    def decorator(func):
        def debounced(*args, **kwargs):
            current_time = time.time()
            if not hasattr(debounced, 'last_called') or (current_time - debounced.last_called > wait):
                result = func(*args, **kwargs)
                debounced.last_called = current_time
                return result
            return None
        return debounced
    return decorator

def async_debounce(wait=3.0):
    def decorator(func):
        last_called = None
        async def debounced(*args, **kwargs):
            nonlocal last_called
            current_time = time.time()
            if last_called is None or (current_time - last_called > wait):
                last_called = current_time
                async for item in func(*args, **kwargs):
                    yield item
            else:
                logger.info(f"MC 查询防抖：间隔太短，忽略本次调用")
                return
        return debounced
    return decorator

# ============ 主题色板 ============
LIGHT_THEME = {
    "bg_start":       (245, 249, 255), "bg_end":         (227, 242, 253),
    "text":           (31, 44, 56, 255), "text_soft":      (76, 90, 103, 255),
    "primary":        (30, 136, 229, 255), "accent":         (66, 165, 245, 255),
    "card_bg":        (255, 255, 255, 180), "card_border":    (255, 255, 255, 230),
    "success":        (46, 125, 50, 255), "error":          (198, 40, 40, 255),
}

DARK_THEME = {
    "bg_start":       (18, 31, 42), "bg_end":         (26, 44, 54),
    "text":           (238, 244, 255, 255), "text_soft":      (176, 190, 197, 255),
    "primary":        (100, 181, 246, 255), "accent":         (144, 202, 249, 255),
    "card_bg":        (0, 0, 0, 150), "card_border":    (255, 255, 255, 60),
    "success":        (129, 199, 132, 255), "error":          (229, 115, 115, 255),
}

# ============ Minecraft 颜色映射 ============
MC_COLORS = {
    'black': '#000000', 'dark_blue': '#0000AA', 'dark_green': '#00AA00',
    'dark_aqua': '#00AAAA', 'dark_red': '#AA0000', 'dark_purple': '#AA00AA',
    'gold': '#FFAA00', 'gray': '#AAAAAA', 'dark_gray': '#555555',
    'blue': '#5555FF', 'green': '#55FF55', 'aqua': '#55FFFF',
    'red': '#FF5555', 'light_purple': '#FF55FF', 'yellow': '#FFFF55',
    'white': '#FFFFFF',
}

LEGACY_CODES = {
    '0': 'black', '1': 'dark_blue', '2': 'dark_green', '3': 'dark_aqua',
    '4': 'dark_red', '5': 'dark_purple', '6': 'gold', '7': 'gray',
    '8': 'dark_gray', '9': 'blue', 'a': 'green', 'b': 'aqua',
    'c': 'red', 'd': 'light_purple', 'e': 'yellow', 'f': 'white',
    'l': 'bold', 'o': 'italic', 'n': 'underlined', 'm': 'strikethrough', 'r': 'reset'
}

# ============ 内置 API 定义 ============
BUILTIN_APIS = {
    "minebbs": { "url": "https://motd.minebbs.com/api/status?ip={ip}&port={port}&stype=auto", "parser": "minebbs" },
    "mcstatus": { "url": "https://api.mcstatus.io/v2/status/java/{ip}:{port}", "parser": "mcstatus" },
    "mcsrvstat": { "url": "https://api.mcsrvstat.us/3/{ip}:{port}", "parser": "mcsrvstat" }
}

@register(
    "astrbot_plugin_mc_motd",
    "无名小服",
    "查询 Minecraft 服务器状态并返回监控面板风格图片（支持多服务器、彩色 MOTD、API故障转移）",
    "v1.6.0",
)
class MCMotdPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

        # ---------- 基础配置 ----------
        self.query_timeout   = self._cfg_int("query_timeout", 10)
        self.default_port    = self._cfg_int("default_port", 25565)
        self.auto_detect     = self._cfg_bool("auto_detect", True)
        self.show_motd       = self._cfg_bool("show_motd", True)
        self.show_players    = self._cfg_bool("show_players", True)
        self.show_version    = self._cfg_bool("show_version", True)
        self.show_delay      = self._cfg_bool("show_delay", True)
        self.card_width      = self._cfg_int("card_width", 900)
        self.font_size       = self._cfg_int("font_size", 28)
        self.theme_mode      = self._cfg_str("theme", "dark")
        self.brand_name      = self._cfg_str("brand_name", "无名小服")
        
        # ---------- API 配置（优先级列表） ----------
        api_priority_str = self._cfg_str("api_priority", "minebbs,mcstatus,mcsrvstat")
        self.api_priority = [s.strip() for s in api_priority_str.split(",") if s.strip()]

        # ---------- 服务器列表 ----------
        servers_raw = self._cfg("servers", "")
        self.servers_list = [s.strip() for s in servers_raw.split(",") if s.strip()] if isinstance(servers_raw, str) else \
                            [str(s).strip() for s in servers_raw if str(s).strip()] if isinstance(servers_raw, list) else []

        self.tmp_dir = "/tmp/astrbot_mc_motd"
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._font_cache: dict = {}
        
        logger.info(f"MC 监控面板已加载 (API优先级: {self.api_priority})")

    # ============ 配置读取辅助 ============
    def _cfg(self, key, default=None):
        try: return self.config.get(key, default) if isinstance(self.config, dict) else default
        except Exception: return default
    def _cfg_bool(self, key, default):
        v = self._cfg(key, default)
        return v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes", "on")
    def _cfg_int(self, key, default):
        try: return int(self._cfg(key, default))
        except Exception: return default
    def _cfg_str(self, key, default):
        v = self._cfg(key, default)
        return str(v) if v is not None else default

    # ============ 字体加载 ============
    def _load_font(self, size: int, bold: bool = False):
        cache_key = f"{size}_{bold}"
        if cache_key in self._font_cache: return self._font_cache[cache_key]
        for name in ["font.ttf", "font.ttc", "font.otf", "main.ttf", "custom.ttf"]:
            path = os.path.join(self.plugin_dir, name)
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    self._font_cache[cache_key] = font
                    return font
                except Exception: continue
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    self._font_cache[cache_key] = font
                    return font
                except Exception: continue
        font = ImageFont.load_default()
        self._font_cache[cache_key] = font
        return font

    def _text_width(self, text, font):
        if not text: return 0
        try: return font.getbbox(text)[2] - font.getbbox(text)[0]
        except AttributeError: return font.getsize(text)[0]
    def _text_height(self, text, font):
        if not text: return 0
        try: return font.getbbox(text)[3] - font.getbbox(text)[1]
        except AttributeError: return font.getsize(text)[1]
    def _resolve_theme(self):
        if self.theme_mode == "light": return "light"
        if self.theme_mode == "dark": return "dark"
        return "dark" if (datetime.now().hour >= 18 or datetime.now().hour < 6) else "light"

    # ============ MOTD 解析逻辑 ============
    def _parse_legacy_string(self, text, inherited_color=None, inherited_bold=False):
        segments, current_color, current_bold = [], inherited_color, inherited_bold
        text = text.replace("\u00a7", "§")
        for part in re.split(r'(§.)', text):
            if not part: continue
            if part.startswith("§"):
                code = part[1].lower()
                if code in LEGACY_CODES:
                    action = LEGACY_CODES[code]
                    if action == 'reset': current_color, current_bold = inherited_color, inherited_bold
                    elif action == 'bold': current_bold = True
                    elif action != 'italic': current_color = action
            else: segments.append({'text': part, 'color': current_color, 'bold': current_bold})
        return segments

    def _parse_motd_components(self, motd_data, inherited_color=None, inherited_bold=False):
        if isinstance(motd_data, str): return self._parse_legacy_string(motd_data, inherited_color, inherited_bold)
        if isinstance(motd_data, list):
            segments = []
            for item in motd_data: segments.extend(self._parse_motd_components(item, inherited_color, inherited_bold))
            return segments
        if isinstance(motd_data, dict):
            color, bold = motd_data.get("color", inherited_color), motd_data.get("bold", inherited_bold)
            text = motd_data.get("text", "")
            if "translate" in motd_data: text = motd_data["translate"] + " " + self._parse_motd_to_plain_text(motd_data.get("with", []))
            segments = [{'text': str(text), 'color': color, 'bold': bold}] if text else []
            if "extra" in motd_data and motd_data["extra"]:
                segments.extend(self._parse_motd_components(motd_data["extra"], color, bold))
            return segments
        return [{'text': str(motd_data), 'color': inherited_color, 'bold': inherited_bold}]

    def _parse_motd_to_plain_text(self, motd_data):
        return "".join(s.get('text', '') for s in self._parse_motd_components(motd_data))

    # ============ API 请求核心（故障转移） ============
    def _normalize_response(self, api_name: str, data: dict, address: str) -> dict:
        try:
            if api_name == "minebbs":
                return {"success": True, "data": data.get("data", data)}
            elif api_name == "mcstatus":
                if not data.get("online"): return {"error": "服务器离线"}
                return {"success": True, "data": {
                    "motd": data.get("motd", {}).get("raw", ""),
                    "players": {"online": data.get("players", {}).get("online", 0), "max": data.get("players", {}).get("max", 0)},
                    "version": data.get("version", {}).get("name_raw", "未知"),
                    "delay": data.get("debug", {}).get("ping", "--"),
                    "favicon": data.get("icon")
                }}
            elif api_name == "mcsrvstat":
                if not data.get("online"): return {"error": "服务器离线"}
                return {"success": True, "data": {
                    "motd": data.get("motd", {}).get("clean", []),
                    "players": {"online": data.get("players", {}).get("online", 0), "max": data.get("players", {}).get("max", 0)},
                    "version": data.get("version", "未知"),
                    "delay": data.get("debug", {}).get("ping", "--"),
                    "favicon": data.get("icon")
                }}
            else: # 自定义 API
                return {"success": True, "data": {
                    "motd": data.get("motd") or data.get("description") or "",
                    "players": {"online": data.get("players", {}).get("online", 0), "max": data.get("players", {}).get("max", 0)},
                    "version": data.get("version", "未知"),
                    "delay": data.get("delay") or data.get("ping", "--"),
                    "favicon": data.get("favicon") or data.get("icon")
                }}
        except Exception as e: return {"error": f"数据解析异常: {str(e)}"}

    @_debounce(wait=3.0)
    def _query_server(self, address: str) -> dict:
        if not HAS_REQUESTS: return {"error": "requests 库未安装"}

        ip, port = address.strip(), self.default_port
        if ":" in ip:
            parts = ip.rsplit(":", 1)
            if parts[1].isdigit(): ip, port = parts[0], int(parts[1])

        # 构建 API 尝试列表（优先用户指定的，然后追加内置未指定的以防万一）
        apis_to_try = self.api_priority.copy()
        for default_api in ["minebbs", "mcstatus", "mcsrvstat"]:
            if default_api not in apis_to_try:
                apis_to_try.append(default_api)

        last_error = "所有 API 查询失败"
        for api_name in apis_to_try:
            if api_name in BUILTIN_APIS:
                url_template, parser = BUILTIN_APIS[api_name]["url"], BUILTIN_APIS[api_name]["parser"]
            else:
                url_template, parser = api_name, "custom"  # 自定义 API 直接当 URL 处理

            url = url_template.replace("{ip}", ip).replace("{port}", str(port))
            try:
                resp = requests.get(url, timeout=self.query_timeout, headers={"User-Agent": "AstrBot-MC-MOTD/1.6"})
                if resp.status_code != 200:
                    last_error = f"API [{api_name}] 状态码 {resp.status_code}"
                    continue
                
                data = resp.json()
                normalized = self._normalize_response(parser, data, address)
                if "error" not in normalized:
                    logger.info(f"MC 查询成功，使用 API: {api_name}")
                    return normalized
                last_error = normalized["error"]
            except Exception as e:
                last_error = f"API [{api_name}] 异常: {str(e)}"
                continue

        return {"error": last_error}

    # ============ 图片绘制核心 ============
    def _create_base(self, width, height, colors, theme):
        base = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(base)
        c1, c2 = colors["bg_start"], colors["bg_end"]
        # 优化背景：深色主题下加入极为微弱的暗色径向渐变，质感更像深邃的夜空
        for y in range(height):
            t = y / max(height - 1, 1)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
        
        # 画一个极暗的中心高光（非常微弱，仅为了打破纯平）
        if theme == "dark":
            glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse([(width//4, height//4), (width*3//4, height*3//4)], fill=(50, 70, 90, 20))
            glow = glow.filter(ImageFilter.GaussianBlur(150))
            base = Image.alpha_composite(base, glow)
        return base

    def _draw_glass_card(self, base, box, radius, colors, favicon_img=None):
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        if w <= 2 or h <= 2: return base

        # 阴影
        shadow = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([(10, 10), (w + 10, h + 10)], radius=radius, fill=(0, 0, 0, 50))
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        base.alpha_composite(shadow, dest=(x1 - 10, y1 - 10))

        glass = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if favicon_img:
            # 将图标放得很大，模糊得非常厉害，叠加深色层，保证只保留淡淡的色彩
            fav_w, fav_h = favicon_img.size
            scale = max(w / fav_w, h / fav_h) * 1.5  # 放大 1.5 倍防止边缘太清晰
            favicon_resized = favicon_img.resize((int(fav_w * scale), int(fav_h * scale)), Image.Resampling.LANCZOS)
            left, top = (favicon_resized.width - w) // 2, (favicon_resized.height - h) // 2
            favicon_cropped = favicon_resized.crop((left, top, left + w, top + h))
            # 高斯模糊半径加大到 40，叠加非常深的黑色半透明，确保背景绝对不抢戏
            favicon_blurred = favicon_cropped.filter(ImageFilter.GaussianBlur(40)).convert("RGBA")
            tint = Image.new("RGBA", (w, h), (0, 0, 0, 200))
            glass = Image.alpha_composite(favicon_blurred, tint)
        else:
            region = base.crop(box).filter(ImageFilter.GaussianBlur(40))
            glass.paste(region, (0, 0))
            glass = Image.alpha_composite(glass, Image.new("RGBA", (w, h), colors["card_bg"]))

        # 极细的边框，增加玻璃质感
        border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, outline=colors["card_border"], width=1)
        
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
        glass.putalpha(mask)
        
        base.alpha_composite(glass, dest=(x1, y1))
        base.alpha_composite(border, dest=(x1, y1))
        return base

    def _draw_motd_text(self, draw, segments, start_x, start_y, max_width, base_font, colors, max_lines=2):
        cur_x, cur_y, lines = start_x, start_y, 1
        line_h = self._text_height("A", base_font) + 8
        for seg in segments:
            text, color_name, is_bold = seg.get('text', ''), seg.get('color'), seg.get('bold', False)
            fill = colors["text"]
            if isinstance(color_name, str):
                if color_name.lower() in MC_COLORS: fill = ImageColor.getrgb(MC_COLORS[color_name.lower()])
                elif color_name.startswith("#"):
                    try: fill = ImageColor.getrgb(color_name)
                    except Exception: pass
            font = self._load_font(int(self.font_size * 0.8), bold=is_bold)
            for ch in text:
                if ch == "\n":
                    lines += 1
                    if lines > max_lines: return cur_y + line_h
                    cur_x, cur_y = start_x, cur_y + line_h
                    continue
                ch_w = self._text_width(ch, font)
                if cur_x + ch_w > start_x + max_width:
                    lines += 1
                    if lines > max_lines: return cur_y + line_h
                    cur_x, cur_y = start_x, cur_y + line_h
                draw.text((cur_x, cur_y), ch, font=font, fill=fill)
                cur_x += ch_w
        return cur_y + line_h

    # ============ 渲染监控面板 ============
    def _render_dashboard(self, addresses: list, results: list) -> bytes:
        theme = self._resolve_theme()
        colors = DARK_THEME if theme == "dark" else LIGHT_THEME

        W, PAD, GAP, CARD_PAD, RAD = max(900, self.card_width), 24, 20, 24, 20
        font_title = self._load_font(int(self.font_size * 1.5), bold=True)
        font_subtitle = self._load_font(int(self.font_size * 0.8))
        font_card_title = self._load_font(int(self.font_size * 1.2), bold=True)
        font_label = self._load_font(int(self.font_size * 0.7))
        font_value = self._load_font(int(self.font_size * 1.4), bold=True)
        font_unit = self._load_font(int(self.font_size * 0.7))
        font_chip = self._load_font(int(self.font_size * 0.7))
        font_motd = self._load_font(int(self.font_size * 0.8))

        cell_h, motd_h = 100, 70
        card_h = 60 + cell_h * 2 + 20 + motd_h + 30
        total_h = 180 + PAD + len(addresses) * (card_h + GAP) + PAD

        base = self._create_base(W, total_h, colors, theme)
        draw = ImageDraw.Draw(base)

        # ---------- 顶部标题与日期时间 ----------
        draw.text((PAD + 20, 30), "MINECRAFT PERFORMANCE", font=font_subtitle, fill=colors["text_soft"])
        draw.text((PAD + 20, 60), "服务器性能监控", font=font_title, fill=colors["text"])
        
        # 右上角：当前年月日与时间
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
        # 计算右上角位置
        right_margin = PAD + 20
        date_w = self._text_width(date_str, font_label)
        time_w = self._text_width(time_str, font_card_title)
        
        draw.text((W - right_margin - date_w, 35), date_str, font=font_label, fill=colors["text_soft"])
        draw.text((W - right_margin - time_w, 60), time_str, font=font_card_title, fill=colors["text"])

        # 顶部信息框
        info_y, info_w = 130, (W - PAD * 2 - GAP * 2) // 3
        for i, (label, val) in enumerate([("显示服务器", f"{len(addresses)} 台"), ("更新时间", now.strftime("%H:%M:%S")), ("监控指标", f"{len(addresses) * 6} 项")]):
            bx1 = PAD + i * (info_w + GAP)
            box_overlay = Image.new("RGBA", (info_w, 65), (0, 0, 0, 0))
            ImageDraw.Draw(box_overlay).rounded_rectangle([(0, 0), (info_w - 1, 64)], radius=12, fill=(255, 255, 255, 20) if theme == "dark" else (0, 0, 0, 20), outline=(255,255,255,40))
            base.alpha_composite(box_overlay, dest=(bx1, info_y))
            draw.text((bx1 + 16, info_y + 10), label, font=font_label, fill=colors["text_soft"])
            draw.text((bx1 + 16, info_y + 32), val, font=font_chip, fill=colors["text"])

        y_offset = info_y + 85

        for idx, (addr, result) in enumerate(zip(addresses, results)):
            card_y1, card_y2, card_x1, card_x2 = y_offset, y_offset + card_h, PAD, W - PAD
            data, error = result.get("data", {}) if result.get("success") else {}, result.get("error")

            motd_raw = data.get("motd") or data.get("description") or "（无 MOTD）"
            motd_segments = self._parse_motd_components(motd_raw)
            version = data.get("version") or data.get("version_name") or "未知"
            if isinstance(version, dict): version = version.get("name", "未知")
            players = data.get("players", {})
            online, max_p = (players.get("online", 0), players.get("max", 0)) if isinstance(players, dict) else (data.get("online", 0), data.get("max", 0))
            delay = data.get("delay") or data.get("latency") or data.get("ping") or "--"
            
            favicon_img = None
            if data.get("favicon"):
                try:
                    b64 = data["favicon"].split(",")[1] if "," in data["favicon"] else data["favicon"]
                    favicon_img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
                except Exception as e: logger.warning(f"解析图标失败: {e}")

            base = self._draw_glass_card(base, (card_x1, card_y1, card_x2, card_y2), RAD, colors, favicon_img)
            draw.text((card_x1 + CARD_PAD, card_y1 + 15), addr, font=font_card_title, fill=colors["text"])
            
            # 右侧可用性标签（去掉色块，保留纯文字）
            online_parts = 6 if not error else 0
            chip_text = f"{online_parts}/6 可用"
            chip_color = colors["success"] if online_parts > 0 else colors["error"]
            chip_w = self._text_width(chip_text, font_chip)
            draw.text((card_x2 - CARD_PAD - chip_w, card_y1 + 20), chip_text, font=font_chip, fill=chip_color)

            # 宫格布局
            grid_y_start = card_y1 + 60
            cell_w = (card_x2 - card_x1 - CARD_PAD * 2 - GAP * 2) // 3
            grid_data = [
                {"label": "延迟 (1分钟)", "value": str(delay), "unit": "ms", "status": "正常" if delay != "--" else "无数据"},
                {"label": "在线玩家", "value": str(online), "unit": "人", "status": "正常"},
                {"label": "最大玩家", "value": str(max_p), "unit": "人", "status": "正常"},
                {"label": "版本", "value": str(version)[:12], "unit": "", "status": "正常"},
                {"label": "状态", "value": "在线" if not error else "离线", "unit": "", "status": "正常" if not error else "无数据"},
                {"label": "类型", "value": "JE/BE", "unit": "", "status": "正常"},
            ]
            for i, cell in enumerate(grid_data):
                cx1 = card_x1 + CARD_PAD + (i % 3) * (cell_w + GAP)
                cy1 = grid_y_start + (i // 3) * (cell_h + 10)
                # 宫格背景
                cell_overlay = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
                ImageDraw.Draw(cell_overlay).rounded_rectangle([(0, 0), (cell_w - 1, cell_h - 1)], radius=10, fill=(255, 255, 255, 15) if theme == "dark" else (0, 0, 0, 15), outline=(255,255,255,40))
                base.alpha_composite(cell_overlay, dest=(cx1, cy1))
                
                # 左上角标签
                draw.text((cx1 + 12, cy1 + 12), cell["label"], font=font_label, fill=colors["text_soft"])
                
                # 右上角状态文字（去除了绿色色块）
                status_text = cell["status"]
                status_color = colors["success"] if status_text == "正常" else colors["error"]
                status_w = self._text_width(status_text, font_label)
                draw.text((cx1 + cell_w - 12 - status_w, cy1 + 14), status_text, font=font_label, fill=status_color)
                
                # 数值
                val_text = str(cell["value"])
                draw.text((cx1 + 12, cy1 + 48), val_text, font=font_value, fill=colors["text"])
                if cell["unit"]:
                    draw.text((cx1 + 12 + self._text_width(val_text, font_value) + 6, cy1 + 62), cell["unit"], font=font_unit, fill=colors["text_soft"])

            # 底部 MOTD
            motd_y = grid_y_start + 2 * (cell_h + 10) + 10
            motd_overlay_w = card_x2 - card_x1 - CARD_PAD * 2
            motd_overlay = Image.new("RGBA", (motd_overlay_w, motd_h), (0, 0, 0, 0))
            ImageDraw.Draw(motd_overlay).rounded_rectangle([(0, 0), (motd_overlay_w - 1, motd_h - 1)], radius=8, fill=(0, 0, 0, 120) if theme == "dark" else (255, 255, 255, 120), outline=(255,255,255,40))
            base.alpha_composite(motd_overlay, dest=(card_x1 + CARD_PAD, motd_y))
            if self.show_motd:
                self._draw_motd_text(draw, motd_segments, card_x1 + CARD_PAD + 16, motd_y + 12, motd_overlay_w - 32, font_motd, colors, max_lines=2)

            y_offset += card_h + GAP

        buf = io.BytesIO()
        base.convert("RGB").save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def _cleanup_tmp(self):
        try:
            now = time.time()
            for f in os.listdir(self.tmp_dir):
                p = os.path.join(self.tmp_dir, f)
                if os.path.isfile(p) and now - os.path.getmtime(p) > 3600: os.remove(p)
        except Exception: pass

    # ============ 指令逻辑 ============
    @async_debounce(wait=3.0)
    @filter.command("mc")
    async def mc_query(self, event: AstrMessageEvent, address: str = None):
        addresses = []
        if address:
            address = address.strip()
            if not re.match(r'^[a-zA-Z0-9\.\-_]+(:\d+)?$', address):
                yield event.plain_result("地址格式不正确。\n示例：mc.example.com 或 mc.example.com:25565")
                return
            addresses.append(address)
        else:
            addresses = self.servers_list
            if not addresses:
                yield event.plain_result("请先在 Web UI 配置服务器地址列表（逗号分隔），\n或使用 /mc <地址> 查询单个服务器。")
                return

        try:
            tasks = [asyncio.to_thread(self._query_server, addr) for addr in addresses]
            results = await asyncio.gather(*tasks)
            img_bytes = await asyncio.to_thread(self._render_dashboard, addresses, results)
            if not img_bytes: raise ValueError("渲染结果为空")
            
            self._cleanup_tmp()
            tmp_path = os.path.join(self.tmp_dir, f"{uuid.uuid4().hex}.png")
            with open(tmp_path, "wb") as f: f.write(img_bytes)
            yield event.image_result(tmp_path)
        except Exception as e:
            logger.error(f"MC 查询失败：{e}")
            yield event.plain_result(f"查询失败：{str(e)}")

    async def terminate(self):
        pass