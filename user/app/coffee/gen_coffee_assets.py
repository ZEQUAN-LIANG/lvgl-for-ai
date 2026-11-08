#!/usr/bin/env python3
"""Generate the AURELIA C9 coffee-machine assets (fonts, cup art, icons).

The generated C headers in this directory are committed. Regenerate them when
the strings in TEXTS change:

    python -I user/app/coffee/gen_coffee_assets.py

Fonts need Node.js (``npx lv_font_conv``) and a CJK TTF on the machine. The
regular/bold files default to DengXian (Deng.ttf / Dengb.ttf) that ships with
Windows. Only the glyphs used by TEXTS plus printable ASCII are embedded.

Cup art is emitted as RGB565 with the card background baked in, so it blends
with the dark cards. Icons are emitted as white ARGB8888 and recolored by the
LVGL style layer.

Previews are optional and never read by the build:

    python -I user/app/coffee/gen_coffee_assets.py --preview <empty-dir>
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Every user-visible string lives here so the font subset and the C labels
# cannot drift apart.
# ---------------------------------------------------------------------------

TEXTS = {
    "BRAND": "AURELIA",
    "BRAND_SUB": "C9 PROFESSIONAL",
    "READY": "就绪",
    "STANDBY": "待机",
    "WAKE": "轻触唤醒",
    "DATE": "11月3日 周二",
    "WEATHER": "上海 · 18°C",
    "WIFI": "Wi-Fi",
    "NAV_COFFEE": "咖啡",
    "NAV_FAVORITES": "收藏",
    "NAV_MAINTENANCE": "养护",
    "NAV_SETTINGS": "设置",
    "GREETING_MORNING": "早上好，",
    "GREETING_AFTERNOON": "下午好，",
    "GREETING_EVENING": "晚上好，",
    "GREETING_SUB": "今天想来一杯什么？",
    "READY_TODAY": "机器已就绪 · 今天第 ",
    "READY_TODAY_SUFFIX": " 杯",
    "MACHINE_STATUS": "机器状态",
    "WATER": "水箱",
    "BEANS": "咖啡豆",
    "MILK": "奶仓",
    "GROUNDS": "渣盒",
    "TODAY": "今日",
    "WEEK": "本周",
    "CUP_UNIT": "杯",
    "STRENGTH": "浓度",
    "VOLUME": "容量",
    "TEMPERATURE": "温度",
    "MILK_AMOUNT": "奶量",
    "FOAM": "奶泡",
    "DOUBLE_CUP": "双杯",
    "PREHEAT_CUP": "预热杯",
    "CUSTOMIZE": "调整配方",
    "BREW": "开始萃取",
    "START_WATER": "开始出水",
    "START_STEAM": "开始打发",
    "CANCELED": "已取消",
    "FAVORITE": "收藏",
    "FAVORITED": "已收藏",
    "ML": "ml",
    "BAR": "bar",
    "DEGREE_C": "°C",
    "DEGREE_F": "°F",
    "PROFILE_0": "Alex",
    "PROFILE_1": "Mia",
    "PROFILE_2": "访客",
    "PROFILE_SWITCHED": "已切换到 ",
    "MON": "一",
    "TUE": "二",
    "WED": "三",
    "THU": "四",
    "FRI": "五",
    "SAT": "六",
    "SUN": "日",
    "D0_NAME": "意式浓缩",
    "D0_IT": "ESPRESSO",
    "D0_DESC": "9 bar 高压萃取，油脂浓郁饱满",
    "D1_NAME": "双份浓缩",
    "D1_IT": "DOPPIO",
    "D1_DESC": "双份粉量，醒神加倍",
    "D2_NAME": "芮斯崔朵",
    "D2_IT": "RISTRETTO",
    "D2_DESC": "精简水量，浓缩风味更集中",
    "D3_NAME": "美式咖啡",
    "D3_IT": "AMERICANO",
    "D3_DESC": "浓缩与热水，清爽而平衡",
    "D4_NAME": "卡布奇诺",
    "D4_IT": "CAPPUCCINO",
    "D4_DESC": "绵密奶泡，经典意式比例",
    "D5_NAME": "拿铁咖啡",
    "D5_IT": "LATTE",
    "D5_DESC": "丝滑牛奶，温柔顺口",
    "D6_NAME": "澳白",
    "D6_IT": "FLAT WHITE",
    "D6_DESC": "双份浓缩，细腻微泡牛奶",
    "D7_NAME": "玛奇朵",
    "D7_IT": "MACCHIATO",
    "D7_DESC": "浓缩点缀奶泡，层次分明",
    "D8_NAME": "摩卡",
    "D8_IT": "MOCHA",
    "D8_DESC": "巧克力与咖啡的浓郁融合",
    "D9_NAME": "冷萃",
    "D9_IT": "COLD BREW",
    "D9_DESC": "低温慢萃，清爽回甘",
    "D10_NAME": "热水",
    "D10_IT": "ACQUA CALDA",
    "D10_DESC": "纯净热水，适合冲泡茶饮",
    "D11_NAME": "蒸汽",
    "D11_IT": "VAPORE",
    "D11_DESC": "手动打发牛奶，绵密奶泡",
    "CUSTOM_TITLE": "自定义配方",
    "CUSTOM_SUB": "调整参数，保存你的专属风味",
    "FOAM_NONE": "无",
    "FOAM_LIGHT": "细腻",
    "FOAM_CREAMY": "绵密",
    "FOAM_RICH": "丰厚",
    "SAVE_RECIPE": "保存配方",
    "SAVE_TO_FAVORITE": "收藏此配方",
    "CANCEL": "取消",
    "DONE": "完成",
    "SAVED": "配方已保存",
    "FAVORITE_ADDED": "已加入收藏",
    "FAVORITE_REMOVED": "已取消收藏",
    "COLD_EXTRACT": "低温萃取",
    "BREWING": "正在制作",
    "PHASE_PREHEAT": "预热",
    "PHASE_GRIND": "研磨",
    "PHASE_PREINFUSE": "预浸",
    "PHASE_EXTRACT": "萃取",
    "PHASE_MILK": "奶泡",
    "PHASE_HEAT_MILK": "加热牛奶",
    "PHASE_FROTH": "打发奶泡",
    "PHASE_WATER": "注水",
    "PHASE_DONE": "完成",
    "STATUS_WAIT": "等待",
    "STATUS_ACTIVE": "进行中",
    "STATUS_DONE": "完成",
    "PRESSURE": "压力",
    "WATER_TEMP": "水温",
    "CANCEL_BREW": "取消萃取",
    "BREW_DONE": "完成 · 请取杯",
    "BREW_DONE_SUB": "祝你今天愉快",
    "TOAST_BREW_DONE": "已完成",
    "TOAST_CANCELED": "已取消萃取",
    "TOAST_LOW_WATER": "水量不足，请加水",
    "TOAST_LOW_BEANS": "咖啡豆不足，请补充",
    "TOAST_LOW_MILK": "奶仓不足，请加奶",
    "TOAST_STANDBY": "已进入待机",
    "TOAST_WAKE": "欢迎回来",
    "ETA": "预计剩余",
    "FAV_TITLE": "我的收藏",
    "FAV_SUB": " 的收藏 · ",
    "FAV_COUNT_SUFFIX": " 款",
    "FAV_EMPTY": "还没有收藏",
    "FAV_EMPTY_HINT": "在咖啡页点击爱心收藏你喜欢的配方",
    "FAV_BREW": "萃取",
    "FAV_EDIT": "调整",
    "MAINT_TITLE": "养护与状态",
    "MAINT_SUB": "保持机器处于最佳状态",
    "SUPPLIES": "补给",
    "RINSE": "日常冲洗",
    "RINSE_DESC": "清除管路中的咖啡残留",
    "MILK_CLEAN": "奶路清洁",
    "MILK_CLEAN_DESC": "清洁奶泡系统与管路",
    "DESCALE": "除垢保养",
    "DESCALE_DESC": "去除加热系统水垢",
    "FILTER": "滤芯寿命",
    "FILTER_DESC": "软化水质，保护锅炉",
    "RUN_RINSE": "运行冲洗",
    "RUN_MILK": "清洁奶路",
    "RUN_DESCALE": "开始除垢",
    "RUN_FILTER": "更换滤芯",
    "GROUNDS_BIN": "咖啡渣盒",
    "EMPTY_GROUNDS": "清空渣盒",
    "REFILL_WATER": "加满水箱",
    "REFILL_BEANS": "补充咖啡豆",
    "REFILL_MILK": "加满奶仓",
    "RINSE_DONE": "日常冲洗已完成",
    "MILK_DONE": "奶路清洁已完成",
    "DESCALE_DONE": "除垢保养已完成",
    "FILTER_DONE": "滤芯已更换",
    "GROUNDS_EMPTIED": "渣盒已清空",
    "WATER_FILLED": "水箱已加满",
    "BEANS_FILLED": "咖啡豆已补充",
    "MILK_FILLED": "奶仓已加满",
    "LAST_RINSE": "上次冲洗：1 天前",
    "BREWS_SINCE": "距上次除垢 ",
    "BREWS_SINCE_SUFFIX": " 杯",
    "BREW_COUNT_LABEL": "萃取次数 ",
    "RUNTIME": "累计运行 128 h",
    "MAINT_PREPARE": "准备中",
    "MAINT_FILL": "注入清洁液",
    "MAINT_CIRCULATE": "循环冲洗",
    "MAINT_RINSE": "清水漂洗",
    "MAINT_FINISH": "完成",
    "SET_TITLE": "设置",
    "SET_SUB": "个性化你的咖啡体验",
    "SET_BREW": "制作设置",
    "SET_SYSTEM": "系统设置",
    "GRIND": "研磨度",
    "COFFEE_TEMP": "咖啡温度",
    "AUTO_OFF": "自动关机",
    "HARDNESS": "水硬度",
    "BRIGHTNESS": "屏幕亮度",
    "SOUND": "提示音",
    "ECO": "节能模式",
    "UNIT": "温度单位",
    "ON": "开启",
    "OFF": "关闭",
    "MIN_15": "15 分钟",
    "MIN_30": "30 分钟",
    "MIN_60": "60 分钟",
    "AUTO_OFF_NEVER": "常亮",
    "HARDNESS_1": "软水",
    "HARDNESS_2": "中等",
    "HARDNESS_3": "偏硬",
    "HARDNESS_4": "硬水",
    "RESET": "恢复默认设置",
    "RESET_CONFIRM": "恢复默认设置？",
    "RESET_CONFIRM_SUB": "所有个性化设置将恢复出厂状态",
    "RESET_DONE": "已恢复默认设置",
    "RESTORE": "恢复",
    "FIRMWARE": "AURELIA OS v3.2.1",
    "FIRMWARE_SUB": "固件 2026.10 · SN C9-8842",
    "TOAST_SETTING": "设置已更新",
    "TEMP_TARGET": "目标 ",
    "PROFILE_OF": " · ",
    "STATUS_OK": "正常",
    "STATUS_LOW": "偏低",
    "DIVIDER": "·",
}

ASCII = "".join(chr(code) for code in range(0x20, 0x7F))


def glyph_corpus() -> str:
    chars = set(ASCII)
    for value in TEXTS.values():
        chars.update(value)
    return "".join(sorted(chars, key=ord))


def cjk_corpus() -> str:
    chars = set()
    for value in TEXTS.values():
        chars.update(char for char in value if ord(char) > 0x7F)
    return "".join(sorted(chars, key=ord))


# ---------------------------------------------------------------------------
# Tiny anti-aliased rasterizer (stdlib only, supersampled)
# ---------------------------------------------------------------------------

WHITE = (1.0, 1.0, 1.0)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def color(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
    )


def mix(a: tuple[float, float, float], b: tuple[float, float, float],
        t: float) -> tuple[float, float, float]:
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


class Raster:
    def __init__(self, width: int, height: int, scale: int = 3) -> None:
        self.w = width
        self.h = height
        self.s = scale
        self.W = width * scale
        self.H = height * scale
        count = self.W * self.H
        self.r = [0.0] * count
        self.g = [0.0] * count
        self.b = [0.0] * count
        self.a = [0.0] * count

    def blend(self, x: int, y: int,
              src: tuple[float, float, float], alpha: float) -> None:
        if alpha <= 0.0 or x < 0 or y < 0 or x >= self.W or y >= self.H:
            return
        if alpha > 1.0:
            alpha = 1.0
        index = y * self.W + x
        dst_a = self.a[index]
        out_a = alpha + dst_a * (1.0 - alpha)
        if out_a <= 0.0:
            return
        factor = dst_a * (1.0 - alpha)
        self.r[index] = (src[0] * alpha + self.r[index] * factor) / out_a
        self.g[index] = (src[1] * alpha + self.g[index] * factor) / out_a
        self.b[index] = (src[2] * alpha + self.b[index] * factor) / out_a
        self.a[index] = out_a

    def _bounds(self, x0: float, y0: float, x1: float,
                y1: float) -> tuple[int, int, int, int]:
        s = self.s
        left = max(0, int(math.floor(x0 * s)) - 1)
        top = max(0, int(math.floor(y0 * s)) - 1)
        right = min(self.W, int(math.ceil(x1 * s)) + 1)
        bottom = min(self.H, int(math.ceil(y1 * s)) + 1)
        return left, top, right, bottom

    def circle(self, cx: float, cy: float, radius: float,
               ink: tuple[float, float, float], alpha: float = 1.0) -> None:
        s = self.s
        scx, scy, sr = cx * s, cy * s, radius * s
        left, top, right, bottom = self._bounds(cx - radius, cy - radius,
                                                cx + radius, cy + radius)
        for y in range(top, bottom):
            dy = (y + 0.5) - scy
            for x in range(left, right):
                dx = (x + 0.5) - scx
                coverage = clamp(sr - math.hypot(dx, dy) + 0.5)
                if coverage > 0.0:
                    self.blend(x, y, ink, alpha * coverage)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float,
                ink: tuple[float, float, float], alpha: float = 1.0) -> None:
        s = self.s
        scx, scy = cx * s, cy * s
        srx, sry = rx * s, ry * s
        left, top, right, bottom = self._bounds(cx - rx, cy - ry,
                                                cx + rx, cy + ry)
        feather = max(1.0, min(srx, sry) * 0.5) / s
        for y in range(top, bottom):
            dy = (y + 0.5 - scy) / sry
            for x in range(left, right):
                dx = (x + 0.5 - scx) / srx
                distance = math.hypot(dx, dy)
                coverage = clamp((1.0 - distance) * min(rx, ry) / feather + 0.5)
                if coverage > 0.0:
                    self.blend(x, y, ink, alpha * coverage)

    def rounded_rect(self, x0: float, y0: float, x1: float, y1: float,
                     radius: float, ink: tuple[float, float, float],
                     alpha: float = 1.0) -> None:
        s = self.s
        sx0, sy0, sx1, sy1 = x0 * s, y0 * s, x1 * s, y1 * s
        sr = radius * s
        cx = (sx0 + sx1) / 2.0
        cy = (sy0 + sy1) / 2.0
        hx = max(0.0, (sx1 - sx0) / 2.0 - sr)
        hy = max(0.0, (sy1 - sy0) / 2.0 - sr)
        left, top, right, bottom = self._bounds(x0, y0, x1, y1)
        for y in range(top, bottom):
            qy = abs((y + 0.5) - cy) - hy
            for x in range(left, right):
                qx = abs((x + 0.5) - cx) - hx
                outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
                inside = min(max(qx, qy), 0.0)
                distance = outside + inside - sr
                coverage = clamp(0.5 - distance)
                if coverage > 0.0:
                    self.blend(x, y, ink, alpha * coverage)

    def clear_ellipse(self, cx: float, cy: float, rx: float,
                      ry: float) -> None:
        s = self.s
        scx, scy = cx * s, cy * s
        srx, sry = rx * s, ry * s
        left, top, right, bottom = self._bounds(cx - rx, cy - ry,
                                                cx + rx, cy + ry)
        feather = max(1.0, min(srx, sry) * 0.5)
        for y in range(top, bottom):
            dy = (y + 0.5 - scy) / sry
            for x in range(left, right):
                dx = (x + 0.5 - scx) / srx
                distance = math.hypot(dx, dy)
                coverage = clamp((1.0 - distance) * min(srx, sry) / feather + 0.5)
                if coverage > 0.0:
                    index = y * self.W + x
                    self.a[index] *= (1.0 - coverage)

    def clear_rounded_rect(self, x0: float, y0: float, x1: float, y1: float,
                           radius: float) -> None:
        s = self.s
        sx0, sy0, sx1, sy1 = x0 * s, y0 * s, x1 * s, y1 * s
        sr = radius * s
        cx = (sx0 + sx1) / 2.0
        cy = (sy0 + sy1) / 2.0
        hx = max(0.0, (sx1 - sx0) / 2.0 - sr)
        hy = max(0.0, (sy1 - sy0) / 2.0 - sr)
        left, top, right, bottom = self._bounds(x0, y0, x1, y1)
        for y in range(top, bottom):
            qy = abs((y + 0.5) - cy) - hy
            for x in range(left, right):
                qx = abs((x + 0.5) - cx) - hx
                outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
                inside = min(max(qx, qy), 0.0)
                distance = outside + inside - sr
                coverage = clamp(0.5 - distance)
                if coverage > 0.0:
                    index = y * self.W + x
                    self.a[index] *= (1.0 - coverage)

    def line(self, x0: float, y0: float, x1: float, y1: float,
             width: float, ink: tuple[float, float, float],
             alpha: float = 1.0) -> None:
        s = self.s
        ax, ay = x0 * s, y0 * s
        bx, by = x1 * s, y1 * s
        half = max(0.5, width * s / 2.0)
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        left, top, right, bottom = self._bounds(
            min(x0, x1) - width, min(y0, y1) - width,
            max(x0, x1) + width, max(y0, y1) + width)
        for y in range(top, bottom):
            py = y + 0.5
            for x in range(left, right):
                px = x + 0.5
                if length2 <= 1e-9:
                    distance = math.hypot(px - ax, py - ay)
                else:
                    t = clamp(((px - ax) * dx + (py - ay) * dy) / length2)
                    distance = math.hypot(px - (ax + t * dx),
                                          py - (ay + t * dy))
                coverage = clamp(half - distance + 0.5)
                if coverage > 0.0:
                    self.blend(x, y, ink, alpha * coverage)

    def polygon(self, points: list[tuple[float, float]],
                ink: tuple[float, float, float], alpha: float = 1.0) -> None:
        if len(points) < 3:
            return
        s = self.s
        scaled = [(x * s, y * s) for x, y in points]
        left, top, right, bottom = self._bounds(
            min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))
        count = len(scaled)
        for y in range(top, bottom):
            py = y + 0.5
            for x in range(left, right):
                px = x + 0.5
                inside = False
                j = count - 1
                for i in range(count):
                    xi, yi = scaled[i]
                    xj, yj = scaled[j]
                    if (yi > py) != (yj > py):
                        cross = (xj - xi) * (py - yi) / (yj - yi) + xi
                        if px < cross:
                            inside = not inside
                    j = i
                if inside:
                    self.blend(x, y, ink, alpha)

    def vertical_gradient(self, y0: float, y1: float,
                          top: tuple[float, float, float],
                          bottom: tuple[float, float, float]) -> None:
        s = self.s
        span = max(1e-6, y1 - y0)
        for y in range(self.H):
            value = clamp(((y + 0.5) / s - y0) / span)
            ink = mix(top, bottom, value)
            for x in range(self.W):
                self.blend(x, y, ink, 1.0)

    def radial_glow(self, cx: float, cy: float, radius: float,
                    ink: tuple[float, float, float], strength: float) -> None:
        s = self.s
        scx, scy, sr = cx * s, cy * s, radius * s
        left, top, right, bottom = self._bounds(cx - radius, cy - radius,
                                                cx + radius, cy + radius)
        for y in range(top, bottom):
            dy = (y + 0.5) - scy
            for x in range(left, right):
                distance = math.hypot((x + 0.5) - scx, dy) / sr
                if distance < 1.0:
                    self.blend(x, y, ink, strength * (1.0 - distance) ** 2)

    def ring(self, cx: float, cy: float, radius: float, width: float,
             ink: tuple[float, float, float], alpha: float = 1.0,
             start: float = 0.0, end: float = 360.0) -> None:
        steps = max(18, int(abs(end - start) / 4.0))
        for i in range(steps):
            a0 = math.radians(start + (end - start) * i / steps)
            a1 = math.radians(start + (end - start) * (i + 1) / steps)
            self.line(cx + radius * math.cos(a0), cy + radius * math.sin(a0),
                      cx + radius * math.cos(a1), cy + radius * math.sin(a1),
                      width, ink, alpha)

    def rgba8(self, grain: float = 0.0,
              seed: int = 1) -> list[tuple[int, int, int, int]]:
        s = self.s
        rng = random.Random(seed)
        pixels: list[tuple[int, int, int, int]] = []
        for y in range(self.h):
            for x in range(self.w):
                sum_r = sum_g = sum_b = sum_a = 0.0
                base = (y * s) * self.W + x * s
                for sy in range(s):
                    row = base + sy * self.W
                    for sx in range(s):
                        index = row + sx
                        alpha = self.a[index]
                        sum_a += alpha
                        sum_r += self.r[index] * alpha
                        sum_g += self.g[index] * alpha
                        sum_b += self.b[index] * alpha
                if sum_a <= 1e-6:
                    pixels.append((0, 0, 0, 0))
                    continue
                red = clamp(sum_r / sum_a)
                green = clamp(sum_g / sum_a)
                blue = clamp(sum_b / sum_a)
                if grain:
                    delta = rng.uniform(-grain, grain) / 255.0
                    red = clamp(red + delta)
                    green = clamp(green + delta)
                    blue = clamp(blue + delta)
                pixels.append((round(red * 255), round(green * 255),
                               round(blue * 255), round(clamp(sum_a / (s * s)) * 255)))
        return pixels

    def rgb565(self, grain: float = 0.0,
               seed: int = 1) -> list[int]:
        rgba = self.rgba8(grain=grain, seed=seed)
        out: list[int] = []
        for red, green, blue, _ in rgba:
            out.append(((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3))
        return out


# ---------------------------------------------------------------------------
# Cup art
# ---------------------------------------------------------------------------

CARD_BG = "#17140F"
GOLD = "#C8A464"
CREAM = "#F2EAD9"
SAUCER = "#D4C9B8"
SAUCER_INNER = "#E9E0D1"


def _rotated_ellipse(cx: float, cy: float, rx: float, ry: float,
                     degrees: float, steps: int = 48) -> list[tuple[float, float]]:
    angle = math.radians(degrees)
    points = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        x = rx * math.cos(t)
        y = ry * math.sin(t)
        points.append((cx + x * math.cos(angle) - y * math.sin(angle),
                       cy + x * math.sin(angle) + y * math.cos(angle)))
    return points


def _crema_ring(r: Raster, cx: float, cy: float, radius: float,
                base: tuple[float, float, float], seed: int) -> None:
    rng = random.Random(seed)
    for i in range(74):
        angle = 2.0 * math.pi * i / 74 + rng.uniform(-0.02, 0.02)
        rr = radius + rng.uniform(-1.8, 1.0)
        x = cx + rr * math.cos(angle)
        y = cy + rr * math.sin(angle)
        ink = mix(base, color("#E8C48B"), rng.uniform(0.1, 0.55))
        r.ellipse(x, y, rng.uniform(1.6, 3.6), rng.uniform(0.9, 2.0),
                  ink, rng.uniform(0.35, 0.75))


def _tiger_stripes(r: Raster, cx: float, cy: float, radius: float,
                   seed: int) -> None:
    rng = random.Random(seed)
    for i in range(14):
        angle = rng.uniform(0, 2 * math.pi)
        start = rng.uniform(radius * 0.4, radius * 0.65)
        length = rng.uniform(radius * 0.12, radius * 0.3)
        x0 = cx + start * math.cos(angle)
        y0 = cy + start * math.sin(angle)
        x1 = cx + (start + length) * math.cos(angle + rng.uniform(-0.2, 0.2))
        y1 = cy + (start + length) * math.sin(angle + rng.uniform(-0.2, 0.2))
        r.line(x0, y0, x1, y1, rng.uniform(0.7, 1.3),
               color("#7A4A22"), rng.uniform(0.12, 0.28))


def _heart(r: Raster, cx: float, cy: float, size: float,
           ink: tuple[float, float, float]) -> None:
    r.circle(cx - size * 0.28, cy - size * 0.22, size * 0.34, ink, 0.95)
    r.circle(cx + size * 0.28, cy - size * 0.22, size * 0.34, ink, 0.95)
    r.polygon([(cx - size * 0.6, cy - size * 0.05),
               (cx + size * 0.6, cy - size * 0.05),
               (cx, cy + size * 0.72)], ink, 0.95)


def _rosetta(r: Raster, cx: float, cy: float, size: float,
             ink: tuple[float, float, float]) -> None:
    for i in range(6):
        t = i / 5.0
        width = size * (0.55 - t * 0.32)
        y = cy - size * 0.36 + t * size * 0.72
        r.ellipse(cx, y, width, size * 0.075, ink, 0.9)
    r.line(cx, cy - size * 0.5, cx, cy + size * 0.46, 2.0, ink, 0.9)


def _swirl(r: Raster, cx: float, cy: float, size: float,
           ink: tuple[float, float, float]) -> None:
    points = []
    for i in range(60):
        t = i / 59.0
        angle = t * math.pi * 3.2
        radius = size * (0.12 + t * 0.42)
        points.append((cx + radius * math.cos(angle),
                       cy + radius * math.sin(angle)))
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        r.line(x0, y0, x1, y1, max(1.2, size * 0.055), ink, 0.85)


def _cocoa_dust(r: Raster, cx: float, cy: float, radius: float,
                seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(90):
        angle = rng.uniform(0, 2 * math.pi)
        rr = radius * math.sqrt(rng.uniform(0, 0.9))
        x = cx + rr * math.cos(angle)
        y = cy + rr * math.sin(angle)
        r.circle(x, y, rng.uniform(0.35, 0.9), color("#5B3218"),
                 rng.uniform(0.3, 0.7))


def _ice_cube(r: Raster, cx: float, cy: float, size: float,
              angle: float, seed: int) -> None:
    a = math.radians(angle)
    half = size * 0.72
    points = []
    for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half)):
        points.append((cx + dx * math.cos(a) - dy * math.sin(a),
                       cy + dx * math.sin(a) + dy * math.cos(a)))
    shadow = [(x + 1.4, y + 1.6) for x, y in points]
    r.polygon(shadow, color("#2B1A10"), 0.35)
    r.polygon(points, color("#EAF2F1"), 0.72)
    inner = [(cx + (x - cx) * 0.72, cy + (y - cy) * 0.72)
             for x, y in points]
    r.polygon(inner, color("#FFFFFF"), 0.22)
    rng = random.Random(seed)
    for _ in range(3):
        a = rng.uniform(0, 2 * math.pi)
        r.line(cx + size * 0.15 * math.cos(a), cy + size * 0.1 * math.sin(a),
               cx + size * 0.5 * math.cos(a), cy + size * 0.35 * math.sin(a),
               0.9, WHITE, 0.5)


def draw_cup(name: str, cfg: dict, width: int = 176, height: int = 176,
             scale: int = 3) -> Raster:
    r = Raster(width, height, scale)
    cx, cy = width * 0.5, height * 0.52
    # Card background: dark espresso with a warm centered glow.
    r.rounded_rect(0, 0, width, height, 0, color(CARD_BG), 1.0)
    r.radial_glow(cx, cy - 4, 88, color("#6B4A2A"), 0.30)
    r.radial_glow(cx, cy - 4, 70, color(GOLD), 0.12)

    cup_r = cfg.get("cup_r", 58.0)
    saucer = cfg.get("saucer", True)
    if saucer:
        r.radial_glow(cx, cy + 6, cup_r + 26, color("#000000"), 0.42)
        r.circle(cx, cy + 3, cup_r + 18, color("#1D1912"), 0.55)
        r.circle(cx, cy, cup_r + 16, color(SAUCER), 1.0)
        r.circle(cx, cy, cup_r + 10, color(SAUCER_INNER), 1.0)
        r.ring(cx, cy, cup_r + 13.2, 0.8, color("#FFFFFF"), 0.28)

    # Cup body and rim.
    r.circle(cx, cy, cup_r, color("#F0E8DA"), 1.0)
    r.circle(cx, cy - 1, cup_r - 3.5, color("#FAF5EB"), 1.0)
    r.ring(cx, cy, cup_r - 0.7, 1.4, color(GOLD), 0.75)
    r.circle(cx, cy + 1, cup_r - 7, color("#D8CCB9"), 1.0)
    r.circle(cx, cy + 1, cup_r - 9.5, color("#EFE6D6"), 1.0)

    liquid_r = cup_r - 9.5
    if cfg.get("water"):
        r.circle(cx, cy + 1, liquid_r, color("#CFE3E1"), 1.0)
        r.circle(cx, cy + 1, liquid_r - 4, color("#DFEFED"), 0.9)
        r.ring(cx, cy + 1, liquid_r - 3, 1.0, color("#FFFFFF"), 0.55)
    elif cfg.get("ice"):
        r.circle(cx, cy + 1, liquid_r, color(cfg.get("coffee", "#8A5528")), 1.0)
        r.circle(cx + 6, cy + 6, liquid_r - 6, color("#6F3F1C"), 0.35)
        for i, (dx, dy, size, angle) in enumerate([
                (-14, -12, 16, 18), (18, -4, 14, -22), (-2, 20, 13, 35)]):
            _ice_cube(r, cx + dx, cy + dy, size, angle, 40 + i)
        for _ in range(16):
            rng = random.Random(90)
            a = rng.uniform(0, 2 * math.pi)
            rr = liquid_r * rng.uniform(0.7, 0.95)
            r.circle(cx + rr * math.cos(a), cy + rr * math.sin(a),
                     1.2, WHITE, 0.35)
    else:
        r.circle(cx, cy + 1, liquid_r, color(cfg.get("coffee", "#3B1E0C")), 1.0)
        r.circle(cx, cy + 1, liquid_r - 4,
                 color(cfg.get("coffee2", "#4A2812")), 0.8)
        _tiger_stripes(r, cx, cy + 1, liquid_r - 6, 7)
        _crema_ring(r, cx, cy + 1, liquid_r - 3,
                    color(cfg.get("crema", "#A66A33")), 11)

        foam = cfg.get("foam", 0)
        if foam > 0:
            foam_r = liquid_r - (2 if foam < 2 else 4)
            r.circle(cx, cy + 1, foam_r, color(cfg.get("foam_color", "#EFE2CE")), 1.0)
            r.circle(cx - 5, cy - 6, foam_r - 8, color("#F7EFE1"), 0.55)
            style = cfg.get("art")
            if style == "heart":
                _heart(r, cx, cy + 2, foam_r * 0.9,
                       color(cfg.get("art_color", "#B57C3E")))
            elif style == "rosetta":
                _rosetta(r, cx, cy + 2, foam_r * 0.95,
                         color(cfg.get("art_color", "#B57C3E")))
            elif style == "swirl":
                _swirl(r, cx, cy + 2, foam_r * 0.95,
                       color(cfg.get("art_color", "#B57C3E")))
            elif style == "dot":
                r.circle(cx, cy + 1, foam_r * 0.38,
                         color(cfg.get("art_color", "#B57C3E")), 0.92)
            if cfg.get("cocoa"):
                _cocoa_dust(r, cx, cy + 1, foam_r * 0.78, 55)
                r.ring(cx, cy + 1, foam_r * 0.8, 2.6, color("#6B3C1D"), 0.55)
            if cfg.get("chocolate"):
                for i in range(5):
                    a = -0.9 + i * 0.42
                    r.line(cx - foam_r * 0.6, cy - foam_r * 0.5 + i * 6,
                           cx + foam_r * 0.6, cy - foam_r * 0.3 + i * 6,
                           2.2, color("#5A2F16"), 0.5)

    # Steam wisps above the cup (subtle, top-down ambience).
    if cfg.get("steam", True):
        rng = random.Random(31)
        for i in range(3):
            x = cx - 22 + i * 22 + rng.uniform(-2, 2)
            points = []
            for j in range(12):
                t = j / 11.0
                points.append((x + math.sin(t * math.pi * 2 + i) * 4.5,
                               cy - cup_r - 2 - t * 26))
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                r.line(x0, y0, x1, y1, 1.6, WHITE, 0.10 + i * 0.02)

    return r


def _ellipse_ring(r: Raster, cx: float, cy: float, rx: float, ry: float,
                  width: float, ink: tuple[float, float, float],
                  alpha: float = 1.0, steps: int = 140) -> None:
    for i in range(steps):
        angle = 2.0 * math.pi * i / steps
        r.circle(cx + rx * math.cos(angle), cy + ry * math.sin(angle),
                 width / 2.0, ink, alpha)


def brew_cup_art() -> Raster:
    """Side-view ceramic cup with a transparent interior hole.

    The C layer draws the animated coffee behind this image; the image supplies
    the saucer, handle, walls and rim. The hole is x=58..132, y=40..128 in
    these 190x170 coordinates.
    """
    r = Raster(190, 170, 3)
    cx = 95.0
    r.radial_glow(cx, 152, 82, color("#000000"), 0.40)
    r.ellipse(cx, 150, 78, 15, color("#C7BCAA"))
    r.ellipse(cx, 150, 70, 11, color("#E9E0D1"))
    _ellipse_ring(r, cx, 150, 74, 13, 1.0, color("#FFFFFF"), 0.25)

    r.ring(148, 94, 27, 9, color("#DCD1C0"))
    r.ring(148, 94, 27, 3, color("#F7F1E6"), 0.45)

    r.rounded_rect(45, 36, 145, 140, 16, color("#EFE6D8"))
    r.rounded_rect(50, 42, 76, 134, 12, color("#F8F3E8"), 0.55)
    r.rounded_rect(118, 42, 142, 134, 10, color("#D8CCB9"), 0.22)
    r.clear_rounded_rect(58, 40, 132, 128, 10)

    r.ellipse(cx, 44, 58, 14, color("#F7F1E6"))
    r.clear_ellipse(cx, 44, 45, 7)
    _ellipse_ring(r, cx, 44, 45, 7, 1.0, color(GOLD), 0.75)
    r.ellipse(cx, 52, 43, 5, color("#B9AB97"), 0.25)
    return r


DRINK_ART = [
    ("espresso", dict(coffee="#2E1608", coffee2="#48230E", crema="#B97B3C",
                      foam=0, cup_r=55)),
    ("doppio", dict(coffee="#2B1407", coffee2="#4A240F", crema="#C08444",
                    foam=0, cup_r=61)),
    ("ristretto", dict(coffee="#2A1306", coffee2="#3F1D0A", crema="#A96A31",
                       foam=0, cup_r=48)),
    ("americano", dict(coffee="#5A3418", coffee2="#6F4420", crema="#9C6A3A",
                       foam=0, cup_r=58)),
    ("cappuccino", dict(coffee="#53300F", coffee2="#6B3E18", crema="#B77B3B",
                        foam=3, art="swirl", cocoa=True, cup_r=59)),
    ("latte", dict(coffee="#4B2A10", coffee2="#6B401D", crema="#B77B3B",
                   foam=2, art="heart", cup_r=60)),
    ("flatwhite", dict(coffee="#45260E", coffee2="#603717", crema="#B77B3B",
                       foam=1, art="rosetta", cup_r=57)),
    ("macchiato", dict(coffee="#2D1507", coffee2="#47230D", crema="#B97B3C",
                       foam=1, art="dot", cup_r=48)),
    ("mocha", dict(coffee="#3E210C", coffee2="#5A3216", crema="#A96A31",
                   foam=2, art="swirl", cocoa=True, chocolate=True, cup_r=60)),
    ("coldbrew", dict(coffee="#7A4A20", ice=True, cup_r=60, steam=False)),
    ("hotwater", dict(water=True, cup_r=57)),
    ("steam", dict(coffee="#E7D6BC", coffee2="#F0E3CE", crema="#EAD8BE",
                   foam=3, art="swirl", foam_color="#F6EDDD", cup_r=59)),
]


# ---------------------------------------------------------------------------
# Icons (white ink; recolored by the LVGL style layer)
# ---------------------------------------------------------------------------

ICON = 28


def _icon() -> Raster:
    return Raster(ICON, ICON, 4)


def _arc(r: Raster, cx: float, cy: float, radius: float, width: float,
         start: float, end: float, alpha: float = 1.0) -> None:
    r.ring(cx, cy, radius, width, WHITE, alpha, start, end)


def icon_bean() -> Raster:
    r = _icon()
    r.polygon(_rotated_ellipse(14, 14, 9.5, 6.2, -32), WHITE, 0.95)
    for i in range(8):
        t = i / 7.0
        x = 8.5 + t * 11.0
        y = 10.0 + t * 8.0
        r.line(x - 1.6, y - 0.8, x + 1.6, y + 0.8, 0.9, (0, 0, 0), 0.85)
    return r


def icon_water() -> Raster:
    r = _icon()
    r.polygon([(14, 2.5), (7.2, 13.5), (7.8, 18.5), (11.0, 23.5),
               (14, 25.0), (17.0, 23.5), (20.2, 18.5), (20.8, 13.5)], WHITE)
    r.circle(14, 18.0, 6.6, WHITE)
    r.ellipse(11.2, 14.8, 2.2, 3.2, (0, 0, 0), 0.55)
    return r


def icon_milk() -> Raster:
    r = _icon()
    r.polygon([(9, 3), (19, 3), (21.5, 7.5), (21.5, 25), (6.5, 25),
               (6.5, 7.5)], WHITE, 0.95)
    r.polygon([(9, 3), (14, 8.5), (19, 3)], (0, 0, 0), 0.55)
    r.line(9.5, 14, 18.5, 14, 1.6, (0, 0, 0), 0.7)
    r.line(9.5, 18, 18.5, 18, 1.6, (0, 0, 0), 0.7)
    return r


def icon_grounds() -> Raster:
    r = _icon()
    r.rounded_rect(7, 8, 21, 25, 2.5, WHITE, 0.95)
    r.rounded_rect(5, 4.5, 23, 8, 1.6, WHITE, 0.95)
    r.rounded_rect(11, 2, 17, 5, 1.2, WHITE, 0.95)
    for x in (11, 14, 17):
        r.line(x, 12, x, 21, 1.2, (0, 0, 0), 0.75)
    return r


def icon_temp() -> Raster:
    r = _icon()
    r.rounded_rect(11.5, 2.5, 16.5, 18, 2.5, WHITE, 0.95)
    r.circle(14, 21.5, 5.4, WHITE, 0.95)
    r.rounded_rect(12.8, 6.5, 15.2, 19, 1.2, (0, 0, 0), 0.75)
    for y in (7.5, 10.5, 13.5, 16.5):
        r.line(18.0, y, 21.0, y, 1.0, WHITE, 0.8)
    return r


def icon_pressure() -> Raster:
    r = _icon()
    r.ring(14, 15, 9.5, 1.7, WHITE, 0.95)
    for i in range(13):
        a = math.radians(150 + i * 20)
        r.line(14 + 7.6 * math.cos(a), 15 + 7.6 * math.sin(a),
               14 + 8.9 * math.cos(a), 15 + 8.9 * math.sin(a), 0.8, WHITE, 0.8)
    r.line(14, 15, 18.5, 9.5, 1.8, WHITE)
    r.circle(14, 15, 1.8, WHITE)
    return r


def icon_clock() -> Raster:
    r = _icon()
    r.ring(14, 14, 10.5, 1.8, WHITE, 0.95)
    r.line(14, 14, 14, 7.5, 1.8, WHITE)
    r.line(14, 14, 19, 16.5, 1.6, WHITE, 0.9)
    r.circle(14, 14, 1.4, WHITE)
    return r


def icon_wifi() -> Raster:
    r = _icon()
    r.circle(14, 22, 2.0, WHITE)
    _arc(r, 14, 22, 6.0, 1.9, 218, 322)
    _arc(r, 14, 22, 10.5, 1.9, 218, 322)
    _arc(r, 14, 22, 15.0, 1.9, 222, 318)
    return r


def icon_gear() -> Raster:
    r = _icon()
    r.circle(14, 14, 7.8, WHITE, 0.95)
    r.circle(14, 14, 3.6, (0, 0, 0), 0.85)
    for i in range(8):
        a = i * math.pi / 4
        x = 14 + 9.6 * math.cos(a)
        y = 14 + 9.6 * math.sin(a)
        r.polygon(_rotated_ellipse(x, y, 2.6, 1.5, math.degrees(a) + 90), WHITE)
    return r


def icon_heart(filled: bool) -> Raster:
    r = _icon()
    if filled:
        _heart(r, 14, 13.5, 12.0, WHITE)
    else:
        _heart(r, 14, 13.5, 12.0, WHITE)
        _heart(r, 14, 13.5, 8.2, (0, 0, 0))
    return r


def icon_star(filled: bool) -> Raster:
    r = _icon()
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = 11.5 if i % 2 == 0 else 5.2
        points.append((14 + radius * math.cos(angle),
                       14.5 + radius * math.sin(angle)))
    r.polygon(points, WHITE, 0.95)
    if not filled:
        inner = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = 8.6 if i % 2 == 0 else 3.5
            inner.append((14 + radius * math.cos(angle),
                          14.5 + radius * math.sin(angle)))
        r.polygon(inner, (0, 0, 0), 0.9)
    return r


def icon_back() -> Raster:
    r = _icon()
    r.line(21, 14, 7, 14, 2.2, WHITE)
    r.line(13, 6, 5.5, 14, 2.2, WHITE)
    r.line(13, 22, 5.5, 14, 2.2, WHITE)
    return r


def icon_chevron_left() -> Raster:
    r = _icon()
    r.line(18, 5, 9, 14, 2.2, WHITE)
    r.line(9, 14, 18, 23, 2.2, WHITE)
    return r


def icon_chevron_right() -> Raster:
    r = _icon()
    r.line(10, 5, 19, 14, 2.2, WHITE)
    r.line(19, 14, 10, 23, 2.2, WHITE)
    return r


def icon_plus() -> Raster:
    r = _icon()
    r.line(14, 5.5, 14, 22.5, 2.4, WHITE)
    r.line(5.5, 14, 22.5, 14, 2.4, WHITE)
    return r


def icon_minus() -> Raster:
    r = _icon()
    r.line(5.5, 14, 22.5, 14, 2.4, WHITE)
    return r


def icon_check() -> Raster:
    r = _icon()
    r.line(5.5, 14.5, 11.0, 20.5, 3.0, WHITE)
    r.line(11.0, 20.5, 22.5, 7.0, 3.0, WHITE)
    return r


def icon_close() -> Raster:
    r = _icon()
    r.line(7, 7, 21, 21, 2.4, WHITE)
    r.line(21, 7, 7, 21, 2.4, WHITE)
    return r


def icon_power() -> Raster:
    r = _icon()
    _arc(r, 14, 15, 9.2, 2.2, 300, 600)
    r.line(14, 3.5, 14, 14, 2.2, WHITE)
    return r


def icon_clean() -> Raster:
    r = _icon()
    r.polygon([(14, 3), (16.2, 11.8), (25, 14), (16.2, 16.2),
               (14, 25), (11.8, 16.2), (3, 14), (11.8, 11.8)], WHITE, 0.95)
    r.circle(21.5, 6.5, 1.6, WHITE, 0.8)
    return r


def icon_descale() -> Raster:
    r = _icon()
    r.polygon([(12, 3), (6.5, 12.5), (7.0, 17.0), (9.5, 21.5),
               (12, 23.0), (14.5, 21.5), (17.0, 17.0), (17.5, 12.5)], WHITE)
    r.circle(12, 16.5, 5.8, WHITE)
    r.polygon([(22, 12), (23.2, 16), (27, 17.2), (23.2, 18.4),
               (22, 22), (20.8, 18.4), (17, 17.2), (20.8, 16)], WHITE, 0.9)
    return r


def icon_filter() -> Raster:
    r = _icon()
    r.polygon([(4, 5), (24, 5), (19, 13), (19, 23), (9, 25),
               (9, 13)], WHITE, 0.95)
    r.polygon([(7.5, 8), (20.5, 8), (17, 12.5), (11, 12.5)],
              (0, 0, 0), 0.8)
    return r


def icon_cup() -> Raster:
    r = _icon()
    r.polygon([(6, 8), (20, 8), (18, 21), (8, 21)], WHITE, 0.95)
    _arc(r, 21, 13.5, 4.2, 1.8, -70, 70)
    r.line(4.5, 24, 21.5, 24, 1.8, WHITE, 0.95)
    r.polygon([(8, 10.5), (18, 10.5), (17, 14), (9, 14)],
              (0, 0, 0), 0.65)
    return r


def icon_steam() -> Raster:
    r = _icon()
    for i, x in enumerate((9.5, 14, 18.5)):
        points = []
        for j in range(14):
            t = j / 13.0
            points.append((x + math.sin(t * math.pi * 2 + i) * 1.8,
                           24 - t * 20))
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            r.line(x0, y0, x1, y1, 1.8, WHITE, 0.9)
    return r


def icon_profile() -> Raster:
    r = _icon()
    r.circle(14, 9.5, 5.0, WHITE, 0.95)
    _arc(r, 14, 24.5, 9.5, 2.4, 200, 340)
    return r


def icon_double_cup() -> Raster:
    r = _icon()
    for dx in (-4, 4):
        r.polygon([(5 + dx, 8), (15 + dx, 8), (13.5 + dx, 20),
                   (6.5 + dx, 20)], WHITE, 0.9)
        _arc(r, 16 + dx, 13, 3.4, 1.5, -70, 70)
    r.line(4, 24, 24, 24, 1.6, WHITE, 0.9)
    return r


def icon_preheat() -> Raster:
    r = _icon()
    r.polygon([(14, 2.5), (21, 12), (20.5, 18), (17.5, 23.5),
               (10.5, 23.5), (7.5, 18), (7, 12)], WHITE, 0.95)
    r.polygon([(14, 11), (17.5, 16), (16.5, 20.5), (14, 22),
               (11.5, 20.5), (10.5, 16)], (0, 0, 0), 0.8)
    return r


def icon_leaf() -> Raster:
    r = _icon()
    points = []
    for i in range(30):
        t = i / 29.0
        points.append((6 + t * 17, 22 - math.sin(t * math.pi) * 15 + t * 2))
    for i in range(29, -1, -1):
        t = i / 29.0
        points.append((6 + t * 17, 22 - math.sin(t * math.pi) * 15 + t * 2 + 4))
    r.polygon(points, WHITE, 0.92)
    r.line(7, 21, 22, 6, 1.2, (0, 0, 0), 0.7)
    return r


def icon_machine() -> Raster:
    r = _icon()
    r.rounded_rect(4, 3, 24, 25, 3.0, WHITE, 0.95)
    r.rounded_rect(7, 6, 21, 12, 1.5, (0, 0, 0), 0.75)
    r.rounded_rect(10, 15, 18, 18, 1.0, (0, 0, 0), 0.75)
    r.circle(19, 21.5, 1.8, (0, 0, 0), 0.75)
    return r


def icon_arrow_right() -> Raster:
    r = _icon()
    r.line(5, 14, 22, 14, 2.0, WHITE)
    r.line(15, 7, 22, 14, 2.0, WHITE)
    r.line(15, 21, 22, 14, 2.0, WHITE)
    return r


def icon_warning() -> Raster:
    r = _icon()
    r.polygon([(14, 3), (26, 24.5), (2, 24.5)], WHITE, 0.95)
    r.line(14, 9.5, 14, 17.5, 2.4, (0, 0, 0))
    r.circle(14, 21.0, 1.6, (0, 0, 0))
    return r


def icon_sound() -> Raster:
    r = _icon()
    r.polygon([(3, 11), (8, 11), (14, 5.5), (14, 22.5), (8, 17), (3, 17)],
              WHITE, 0.95)
    _arc(r, 15, 14, 4.5, 1.8, -55, 55)
    _arc(r, 15, 14, 8.5, 1.8, -50, 50)
    return r


def icon_brightness() -> Raster:
    r = _icon()
    r.circle(14, 14, 5.5, WHITE, 0.95)
    for i in range(8):
        a = i * math.pi / 4
        r.line(14 + 8.2 * math.cos(a), 14 + 8.2 * math.sin(a),
               14 + 12.0 * math.cos(a), 14 + 12.0 * math.sin(a), 1.8, WHITE)
    return r


def icon_eco() -> Raster:
    r = _icon()
    r.ring(14, 14, 11, 1.6, WHITE, 0.9)
    r.polygon([(9, 19), (10, 10), (20, 8), (18.5, 18), (13, 16)],
              WHITE, 0.95)
    return r


def icon_info() -> Raster:
    r = _icon()
    r.ring(14, 14, 10.5, 1.8, WHITE, 0.95)
    r.circle(14, 8.5, 1.7, WHITE)
    r.rounded_rect(12.8, 12, 15.2, 21, 1.1, WHITE)
    return r


ARGB_ART = [
    ("coffee_brew_cup", brew_cup_art),
]

ICONS = {
    "bean": icon_bean,
    "water": icon_water,
    "milk": icon_milk,
    "grounds": icon_grounds,
    "temp": icon_temp,
    "pressure": icon_pressure,
    "clock": icon_clock,
    "wifi": icon_wifi,
    "gear": icon_gear,
    "heart": lambda: icon_heart(False),
    "heart_filled": lambda: icon_heart(True),
    "star": lambda: icon_star(False),
    "star_filled": lambda: icon_star(True),
    "back": icon_back,
    "chevron_left": icon_chevron_left,
    "chevron_right": icon_chevron_right,
    "plus": icon_plus,
    "minus": icon_minus,
    "check": icon_check,
    "close": icon_close,
    "power": icon_power,
    "clean": icon_clean,
    "descale": icon_descale,
    "filter": icon_filter,
    "cup": icon_cup,
    "steam": icon_steam,
    "profile": icon_profile,
    "double_cup": icon_double_cup,
    "preheat": icon_preheat,
    "leaf": icon_leaf,
    "machine": icon_machine,
    "arrow_right": icon_arrow_right,
    "warning": icon_warning,
    "sound": icon_sound,
    "brightness": icon_brightness,
    "eco": icon_eco,
    "info": icon_info,
}


# ---------------------------------------------------------------------------
# C emission
# ---------------------------------------------------------------------------


def emit_texts() -> None:
    lines = [
        "/* Generated by gen_coffee_assets.py; do not edit by hand. */",
        "#ifndef COFFEE_TEXTS_H",
        "#define COFFEE_TEXTS_H",
        "",
    ]
    for key, value in TEXTS.items():
        lines.append(f'#define COFFEE_TXT_{key} "{value}"')
    lines += ["", "#endif /* COFFEE_TEXTS_H */", ""]
    (HERE / "coffee_texts.h").write_text("\n".join(lines), encoding="utf-8")


def _emit_u16(values: list[int], name: str) -> list[str]:
    lines = [f"static const uint16_t {name}[] = {{"]
    for start in range(0, len(values), 12):
        chunk = ", ".join(f"0x{value:04X}" for value in values[start:start + 12])
        lines.append(f"    {chunk},")
    lines.append("};")
    return lines


def _emit_u32(values: list[int], name: str) -> list[str]:
    lines = [f"static const uint32_t {name}[] = {{"]
    for start in range(0, len(values), 8):
        chunk = ", ".join(f"0x{value:08X}" for value in values[start:start + 8])
        lines.append(f"    {chunk},")
    lines.append("};")
    return lines


def write_png(path: Path, width: int, height: int,
              pixels: list[tuple[int, int, int]]) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            red, green, blue = pixels[y * width + x]
            raw += bytes((red, green, blue))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           chunk(b"IEND", b""))
    path.write_bytes(png)


def emit_images(preview_dir: Path | None) -> None:
    lines = [
        "/* Generated by gen_coffee_assets.py; do not edit by hand. */",
        "#ifndef COFFEE_IMAGES_H",
        "#define COFFEE_IMAGES_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    preview_dir and preview_dir.mkdir(parents=True, exist_ok=True)

    for index, (name, cfg) in enumerate(DRINK_ART):
        raster = draw_cup(name, cfg)
        pixels = raster.rgb565(grain=1.6, seed=200 + index)
        if preview_dir:
            rgba = raster.rgba8(grain=1.6, seed=200 + index)
            write_png(preview_dir / f"coffee_{name}.png", raster.w, raster.h,
                      [(r, g, b) for r, g, b, _ in rgba])
        symbol = f"coffee_art_{name}"
        lines += [f"#define {symbol.upper()}_W {raster.w}",
                  f"#define {symbol.upper()}_H {raster.h}", ""]
        lines += _emit_u16(pixels, f"{symbol}_data")
        lines += [
            f"static const lv_image_dsc_t {symbol} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_RGB565,",
            "        .flags = 0,",
            f"        .w = {raster.w},",
            f"        .h = {raster.h},",
            f"        .stride = {raster.w * 2},",
            "        .reserved_2 = 0,",
            "    },",
            f"    .data_size = sizeof({symbol}_data),",
            f"    .data = (const uint8_t *){symbol}_data,",
            "};",
            "",
        ]

    for key, draw in ICONS.items():
        raster = draw()
        rgba = raster.rgba8()
        values = [(a << 24) | (r << 16) | (g << 8) | b
                  for r, g, b, a in rgba]
        if preview_dir:
            flattened = []
            for red, green, blue, alpha in rgba:
                t = alpha / 255.0
                flattened.append((round(red * t + 23 * (1 - t)),
                                  round(green * t + 20 * (1 - t)),
                                  round(blue * t + 15 * (1 - t))))
            write_png(preview_dir / f"icon_{key}.png", raster.w, raster.h,
                      flattened)
        symbol = f"coffee_icon_{key}"
        lines += [f"#define {symbol.upper()}_W {raster.w}",
                  f"#define {symbol.upper()}_H {raster.h}", ""]
        lines += _emit_u32(values, f"{symbol}_data")
        lines += [
            f"static const lv_image_dsc_t {symbol} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_ARGB8888,",
            "        .flags = 0,",
            f"        .w = {raster.w},",
            f"        .h = {raster.h},",
            f"        .stride = {raster.w * 4},",
            "        .reserved_2 = 0,",
            "    },",
            f"    .data_size = sizeof({symbol}_data),",
            f"    .data = (const uint8_t *){symbol}_data,",
            "};",
            "",
        ]

    for symbol, draw in ARGB_ART:
        raster = draw()
        rgba = raster.rgba8()
        values = [(a << 24) | (r << 16) | (g << 8) | b
                  for r, g, b, a in rgba]
        if preview_dir:
            flattened = []
            for red, green, blue, alpha in rgba:
                t = alpha / 255.0
                flattened.append((round(red * t + 23 * (1 - t)),
                                  round(green * t + 20 * (1 - t)),
                                  round(blue * t + 15 * (1 - t))))
            write_png(preview_dir / f"{symbol}.png", raster.w, raster.h,
                      flattened)
        lines += [f"#define {symbol.upper()}_W {raster.w}",
                  f"#define {symbol.upper()}_H {raster.h}", ""]
        lines += _emit_u32(values, f"{symbol}_data")
        lines += [
            f"static const lv_image_dsc_t {symbol} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_ARGB8888,",
            "        .flags = 0,",
            f"        .w = {raster.w},",
            f"        .h = {raster.h},",
            f"        .stride = {raster.w * 4},",
            "        .reserved_2 = 0,",
            "    },",
            f"    .data_size = sizeof({symbol}_data),",
            f"    .data = (const uint8_t *){symbol}_data,",
            "};",
            "",
        ]

    lines += ["#endif /* COFFEE_IMAGES_H */", ""]
    (HERE / "coffee_images.h").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONTS = [
    ("coffee_font_12", "regular", 12),
    ("coffee_font_13", "regular", 13),
    ("coffee_font_14", "regular", 14),
    ("coffee_font_14b", "bold", 14),
    ("coffee_font_16", "regular", 16),
    ("coffee_font_18b", "bold", 18),
    ("coffee_font_24b", "bold", 24),
    ("coffee_font_32b", "bold", 32),
    ("coffee_font_44b", "bold", 44),
]


def font_hash(regular: Path, bold: Path) -> str:
    digest = hashlib.sha256()
    digest.update(glyph_corpus().encode("utf-8"))
    for path in (regular, bold):
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(str(path).encode("utf-8"))
    digest.update(repr(FONTS).encode("ascii"))
    return digest.hexdigest()


def generate_fonts(regular: Path, bold: Path, force: bool) -> None:
    stamp = HERE / "coffee_fonts.sha256"
    signature = font_hash(regular, bold)
    if (not force and stamp.is_file() and
            stamp.read_text(encoding="utf-8").strip() == signature and
            all((HERE / f"{name}.h").is_file() for name, _, _ in FONTS)):
        return

    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx not found; install Node.js to regenerate fonts")
    source = {"regular": regular, "bold": bold}
    for name, weight, size in FONTS:
        output = HERE / f"{name}.c"
        command = [
            npx, "--yes", "lv_font_conv",
            "--font", str(source[weight]),
            "--size", str(size),
            "--bpp", "4",
            "--no-compress",
            "--no-kerning",
            "--format", "lvgl",
            "--lv-font-name", name,
            "-o", str(output),
            "-r", "0x20-0x7E",
            "--symbols", cjk_corpus(),
        ]
        print(f"font: {name} ({weight}, {size}px)")
        subprocess.run(command, check=True, cwd=HERE,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        text = output.read_text(encoding="utf-8")
        text = text.replace(f"const lv_font_t {name} =",
                            f"static const lv_font_t {name} =")
        text = text.replace("uint8_t glyph_bitmap[]",
                            f"uint8_t {name}_glyph_bitmap[]")
        text = text.replace(".glyph_bitmap = glyph_bitmap,",
                            f".glyph_bitmap = {name}_glyph_bitmap,")
        text = text.replace("lv_font_fmt_txt_glyph_dsc_t glyph_dsc[]",
                            f"lv_font_fmt_txt_glyph_dsc_t {name}_glyph_dsc[]")
        text = text.replace(".glyph_dsc = glyph_dsc,",
                            f".glyph_dsc = {name}_glyph_dsc,")
        text = re.sub(
            r"static const uint16_t (unicode_list_\d+)\[\]",
            rf"static const uint16_t {name}_\1[]", text)
        text = re.sub(
            r"\.unicode_list = (unicode_list_\d+),",
            rf".unicode_list = {name}_\1,", text)
        text = text.replace("lv_font_fmt_txt_cmap_t cmaps[]",
                            f"lv_font_fmt_txt_cmap_t {name}_cmaps[]")
        text = text.replace(".cmaps = cmaps,",
                            f".cmaps = {name}_cmaps,")
        text = text.replace("lv_font_fmt_txt_dsc_t font_dsc =",
                            f"lv_font_fmt_txt_dsc_t {name}_font_dsc =")
        text = text.replace(".dsc = &font_dsc,",
                            f".dsc = &{name}_font_dsc,")
        text = text.replace("lv_font_fmt_txt_glyph_cache_t cache;",
                            f"lv_font_fmt_txt_glyph_cache_t {name}_cache;")
        text = text.replace(".cache = &cache", f".cache = &{name}_cache")
        header = (
            f"/* Generated by gen_coffee_assets.py from {source[weight].name};"
            " do not edit. */\n" + text)
        (HERE / f"{name}.h").write_text(header, encoding="utf-8")
        output.unlink()

    stamp.write_text(signature + "\n", encoding="utf-8")


def emit_aggregate() -> None:
    lines = [
        "/* Generated by gen_coffee_assets.py; do not edit by hand. */",
        "#ifndef COFFEE_ASSETS_H",
        "#define COFFEE_ASSETS_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    for name, _, _ in FONTS:
        lines.append(f'#include "{name}.h"')
    lines += ['#include "coffee_images.h"', "", "#endif /* COFFEE_ASSETS_H */", ""]
    (HERE / "coffee_assets.h").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-regular", default="C:/Windows/Fonts/Deng.ttf")
    parser.add_argument("--font-bold", default="C:/Windows/Fonts/Dengb.ttf")
    parser.add_argument("--force-fonts", action="store_true")
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()

    regular = Path(args.font_regular)
    bold = Path(args.font_bold)
    generate_fonts(regular, bold, args.force_fonts)
    emit_texts()
    emit_images(args.preview)
    emit_aggregate()
    print(f"wrote assets to {HERE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
