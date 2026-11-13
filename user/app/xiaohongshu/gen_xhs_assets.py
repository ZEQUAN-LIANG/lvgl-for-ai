#!/usr/bin/env python3
"""Generate the Xiaohongshu page assets (fonts, cover art, icons).

The generated C headers in this directory are committed. Regenerate them when
the strings in TEXTS change:

    python -I user/app/xiaohongshu/gen_xhs_assets.py

Fonts need Node.js (``npx lv_font_conv``) and a CJK TTF on the machine. The
regular/bold files default to DengXian (Deng.ttf / Dengb.ttf) that ships with
Windows. Only the glyphs used by TEXTS plus printable ASCII are embedded.

Previews are optional and never read by the build:

    python -I user/app/xiaohongshu/gen_xhs_assets.py --preview <empty-dir>
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
# Strings used by user/app/xiaohongshu/xhs_page.c. Keep every user-visible
# string here so
# the font subset and the C labels cannot drift apart.
# ---------------------------------------------------------------------------

TEXTS = {
    "LOGO": "小红书",
    "TAB_FOLLOW": "关注",
    "TAB_FOR_YOU": "发现",
    "TAB_NEARBY": "附近",
    "CAT_RECOMMEND": "推荐",
    "CAT_LIVE": "直播",
    "CAT_DRAMA": "短剧",
    "CAT_OUTFIT": "穿搭",
    "CAT_TRAVEL": "旅行",
    "CAT_ANIME": "动漫",
    "NAV_HOME": "首页",
    "NAV_MARKET": "市集",
    "NAV_MESSAGE": "消息",
    "NAV_ME": "我",
    "FOLLOW": "关注",
    "FOLLOWED": "已关注",
    "JUST_NOW": "刚刚更新",
    "DETAIL_EDITED": "编辑于 10-28",
    "DETAIL_LIKE": "点赞",
    "DETAIL_COLLECT": "收藏",
    "DETAIL_COMMENT": "评论",
    "DETAIL_INPUT": "说点什么...",
    "DETAIL_COMMENTS": "共 %d 条评论",
    "COMMENT_0_NAME": "momo",
    "COMMENT_0_TEXT": "好治愈啊，收藏了！",
    "COMMENT_1_NAME": "阿柴",
    "COMMENT_1_TEXT": "求蹲一个地址～",
    "COMMENT_2_NAME": "小鹿",
    "COMMENT_2_TEXT": "照片拍得好好看",
    "NOTE_0_TITLE": "小狗喜欢阳光和草地",
    "NOTE_0_AUTHOR": "daitu琳",
    "NOTE_0_AVATAR": "琳",
    "NOTE_0_BODY": "午后的草地上，小狗追着光斑跑了一下午。",
    "NOTE_0_TAG": "#周末去哪儿",
    "NOTE_0_LOCATION": "上海·徐汇滨江",
    "NOTE_1_TITLE": "一些纸片子和古早小垃圾记录",
    "NOTE_1_AUTHOR": "唧唧",
    "NOTE_1_AVATAR": "唧",
    "NOTE_1_BODY": "翻出收集多年的纸片和小卡，每一张都藏着一段回忆。",
    "NOTE_1_TAG": "#手账收藏",
    "NOTE_1_LOCATION": "上海·静安",
    "NOTE_2_TITLE": "周末做了焦糖布丁，太治愈了",
    "NOTE_2_AUTHOR": "厨房小记",
    "NOTE_2_AVATAR": "厨",
    "NOTE_2_BODY": "第一次尝试焦糖布丁，焦糖脆脆的，布丁入口即化。",
    "NOTE_2_TAG": "#下午茶",
    "NOTE_2_LOCATION": "上海·长宁",
    "NOTE_3_TITLE": "徒步之旅认识的朋友",
    "NOTE_3_AUTHOR": "谢羽琪",
    "NOTE_3_AVATAR": "谢",
    "NOTE_3_BODY": "在山顶看日落，认识了一群同样热爱徒步的朋友。",
    "NOTE_3_TAG": "#徒步日记",
    "NOTE_3_LOCATION": "杭州·西湖群山",
    "NOTE_4_TITLE": "绿草地上的竞技从不缺故事与记录",
    "NOTE_4_AUTHOR": "运动日记",
    "NOTE_4_AVATAR": "运",
    "NOTE_4_BODY": "草地网球局，笑声比比分更精彩。",
    "NOTE_4_TAG": "#运动日常",
    "NOTE_4_LOCATION": "上海·世纪公园",
    "NOTE_5_TITLE": "秋日穿搭｜奶油色系的一周",
    "NOTE_5_AUTHOR": "Miya",
    "NOTE_5_AVATAR": "M",
    "NOTE_5_BODY": "奶油色系一周穿搭，温柔又显气质。",
    "NOTE_5_TAG": "#秋冬穿搭",
    "NOTE_5_LOCATION": "上海·安福路",
    "NEARBY_0": "1.2km",
    "NEARBY_1": "1.8km",
    "NEARBY_2": "2.4km",
    "NEARBY_3": "3.6km",
    "NEARBY_4": "4.1km",
    "NEARBY_5": "5.0km",
    "MARKET_TITLE": "市集",
    "MARKET_BANNER_TITLE": "秋日好物节",
    "MARKET_BANNER_SUB": "精选好物 低至 5 折",
    "MARKET_ALL": "推荐",
    "MARKET_BEAUTY": "美妆",
    "MARKET_HOME": "家居",
    "MARKET_DIGITAL": "数码",
    "MARKET_FOOD": "美食",
    "MARKET_SPORT": "运动",
    "MARKET_EMPTY": "更多好物正在上架",
    "MARKET_DETAIL": "商品详情",
    "MARKET_GUARANTEE": "品质保障 · 7 天无理由退换 · 顺丰包邮",
    "ADD_CART": "加入购物车",
    "ADDED_CART": "已加入购物车",
    "PRODUCT_0_NAME": "奶油风陶瓷马克杯",
    "PRODUCT_0_PRICE": "39",
    "PRODUCT_0_SALES": "2.3万+人付款",
    "PRODUCT_1_NAME": "羊羔绒针织开衫",
    "PRODUCT_1_PRICE": "129",
    "PRODUCT_1_SALES": "8600+人付款",
    "PRODUCT_2_NAME": "复古胶片相机",
    "PRODUCT_2_PRICE": "268",
    "PRODUCT_2_SALES": "1200+人付款",
    "PRODUCT_3_NAME": "手作香薰蜡烛",
    "PRODUCT_3_PRICE": "59",
    "PRODUCT_3_SALES": "1.1万+人付款",
    "YUAN": "¥",
    "MSG_TITLE": "消息",
    "MSG_LIKE": "赞和收藏",
    "MSG_FOLLOW": "新增关注",
    "MSG_COMMENT": "评论和@",
    "MSG_DM": "私信",
    "MSG_ROW_0_NAME": "Miya",
    "MSG_ROW_0_TEXT": "你分享的穿搭太好看了！",
    "MSG_ROW_0_TIME": "10:24",
    "MSG_ROW_1_NAME": "厨房小记",
    "MSG_ROW_1_TEXT": "布丁的配方已经发你啦",
    "MSG_ROW_1_TIME": "昨天",
    "MSG_ROW_2_NAME": "运动日记",
    "MSG_ROW_2_TEXT": "周末一起打球吗？",
    "MSG_ROW_2_TIME": "周日",
    "MSG_ROW_3_NAME": "小红书通知",
    "MSG_ROW_3_TEXT": "你的笔记获得 100 个赞",
    "MSG_ROW_3_TIME": "10-26",
    "CHAT_INPUT": "发消息...",
    "CHAT_SEND": "发送",
    "CHAT_BUBBLE_0": "嗨！看到你发的笔记啦",
    "CHAT_BUBBLE_1": "谢谢喜欢～",
    "CHAT_BUBBLE_2": "周末有空一起去看展吗？",
    "CHAT_REPLY": "好的，晚点聊！",
    "CHANNEL_ITEM_0": "momo 赞了你的笔记",
    "CHANNEL_ITEM_1": "阿柴 收藏了你的笔记",
    "CHANNEL_ITEM_2": "小鹿 评论了你：好治愈啊！",
    "CHANNEL_TIME_0": "10:02",
    "CHANNEL_TIME_1": "昨天",
    "CHANNEL_TIME_2": "10-27",
    "PROFILE_NAME": "小红薯",
    "PROFILE_ID": "小红书号：123456789",
    "PROFILE_BIO": "记录生活里的小确幸",
    "PROFILE_LOCATION": "上海",
    "PROFILE_EDIT": "编辑资料",
    "STAT_FOLLOW": "关注",
    "STAT_FANS": "粉丝",
    "STAT_LIKES": "获赞与收藏",
    "STAT_FOLLOW_N": "128",
    "STAT_FANS_N": "2.4万",
    "STAT_LIKES_N": "12.8万",
    "PROFILE_NOTES": "笔记",
    "PROFILE_FAV": "收藏",
    "PROFILE_LIKED": "赞过",
    "PUBLISH_TITLE": "发布笔记",
    "PUBLISH_DRAFT": "存草稿",
    "PUBLISH_PHOTO": "图文",
    "PUBLISH_VIDEO": "视频",
    "PUBLISH_LIVE": "直播",
    "PUBLISH_ADD_IMAGE": "添加图片",
    "PUBLISH_TITLE_HINT": "填写标题会有更多赞哦～",
    "PUBLISH_BODY_HINT": "分享你的生活、经验和好物...",
    "PUBLISH_LOCATION": "添加地点",
    "PUBLISH_TAG": "添加标签",
    "PUBLISH_VISIBLE": "谁可以看",
    "PUBLISH_PUBLIC": "公开",
    "PUBLISH_PRIVATE": "仅自己可见",
    "PUBLISH_SUBMIT": "发布",
    "PUBLISH_SUCCESS": "发布成功",
    "PUBLISH_SUCCESS_SUB": "你的笔记已经发布到小红书",
    "PUBLISH_DONE": "完成",
    "PUBLISH_SAVED": "草稿已保存",
    "SEARCH_PLACEHOLDER": "搜索用户、笔记",
    "SEARCH_CANCEL": "取消",
    "SEARCH_ACTION": "搜索",
    "SEARCH_HISTORY": "历史搜索",
    "SEARCH_SUGGEST": "猜你想搜",
    "SEARCH_HISTORY_0": "夏日穿搭",
    "SEARCH_HISTORY_1": "咖啡店",
    "SEARCH_HISTORY_2": "徒步",
    "SEARCH_SUGGEST_0": "秋天第一杯奶茶",
    "SEARCH_SUGGEST_1": "周末去哪儿",
    "SEARCH_SUGGEST_2": "小狗日常",
    "CAT_MORE_0": "美食",
    "CAT_MORE_1": "彩妆",
    "CAT_MORE_2": "影视",
    "CAT_MORE_3": "职场",
    "CAT_MORE_4": "情感",
    "CAT_MORE_5": "家居",
}

ASCII = "".join(chr(code) for code in range(0x20, 0x7F))


def glyph_corpus() -> str:
    chars = set(ASCII)
    for value in TEXTS.values():
        chars.update(value)
    return "".join(sorted(chars, key=ord))


def cjk_corpus() -> str:
    """Non-ASCII glyphs only; passed through a Windows .CMD without metachars."""
    chars = set()
    for value in TEXTS.values():
        chars.update(char for char in value if ord(char) > 0x7F)
    return "".join(sorted(chars, key=ord))


# ---------------------------------------------------------------------------
# Tiny anti-aliased rasterizer (stdlib only, supersampled)
# ---------------------------------------------------------------------------


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = clamp((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


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


def rotate(px: float, py: float, cx: float, cy: float,
           degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    dx = px - cx
    dy = py - cy
    return (cx + dx * math.cos(radians) - dy * math.sin(radians),
            cy + dx * math.sin(radians) + dy * math.cos(radians))


def rotated_rect(cx: float, cy: float, width: float, height: float,
                 degrees: float) -> list[tuple[float, float]]:
    corners = [
        (cx - width / 2, cy - height / 2),
        (cx + width / 2, cy - height / 2),
        (cx + width / 2, cy + height / 2),
        (cx - width / 2, cy + height / 2),
    ]
    return [rotate(x, y, cx, cy, degrees) for x, y in corners]


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

    def vignette(self, strength: float) -> None:
        s = self.s
        half_w = self.W / 2.0
        half_h = self.H / 2.0
        normalizer = math.hypot(half_w, half_h)
        black = (0.0, 0.0, 0.0)
        for y in range(self.H):
            dy = (y + 0.5) - half_h
            for x in range(self.W):
                dx = (x + 0.5) - half_w
                distance = math.hypot(dx, dy) / normalizer
                alpha = strength * smoothstep(0.30, 1.0, distance)
                if alpha > 0.0:
                    self.blend(x, y, black, alpha)

    def rgba8(self, grain: float = 0.0,
              seed: int = 1) -> list[tuple[int, int, int, int]]:
        s = self.s
        block = s * s
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
                alpha = clamp(sum_a / block)
                pixels.append((round(red * 255), round(green * 255),
                               round(blue * 255), round(alpha * 255)))
        return pixels

    def rgb565(self, grain: float = 0.0,
               seed: int = 1) -> list[int]:
        values = []
        for red, green, blue, _ in self.rgba8(grain, seed):
            values.append(((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3))
        return values


# ---------------------------------------------------------------------------
# Cover art
# ---------------------------------------------------------------------------

WHITE = color("#FFFFFF")
INK = color("#2B2118")


def cover_dog(r: Raster) -> None:
    w, h = r.w, r.h
    r.vertical_gradient(0, h, color("#A9CBE6"), color("#EAF4F6"))

    r.circle(w * 0.78, h * 0.18, h * 0.10, color("#FFE7A8"), 0.18)
    r.circle(w * 0.78, h * 0.18, h * 0.065, color("#FFE7A8"), 0.92)
    r.ellipse(w * 0.22, h * 0.17, w * 0.16, h * 0.035, WHITE, 0.75)
    r.ellipse(w * 0.30, h * 0.15, w * 0.10, h * 0.028, WHITE, 0.65)
    r.ellipse(w * 0.13, h * 0.22, w * 0.09, h * 0.022, WHITE, 0.45)

    r.polygon([(0, h * 0.62), (w * 0.24, h * 0.51), (w * 0.50, h * 0.60),
               (w * 0.76, h * 0.52), (w, h * 0.62), (w, h * 0.72), (0, h * 0.72)],
              color("#A9C58F"))

    r.vertical_gradient(h * 0.62, h, color("#8CB466"), color("#5B8743"))

    rng = random.Random(11)
    for _ in range(150):
        x = rng.uniform(0, w)
        y = rng.uniform(h * 0.64, h * 0.99)
        r.line(x, y, x + rng.uniform(-2.5, 2.5), y - rng.uniform(3, 9),
               0.9, color("#6D9A4D"), 0.55)

    # Soft shadow under the corgi.
    r.ellipse(w * 0.50, h * 0.905, w * 0.27, h * 0.038,
              color("#3D5C2B"), 0.35)

    # Legs and paws.
    r.rounded_rect(w * 0.39, h * 0.78, w * 0.47, h * 0.91, 4,
                   color("#D08B4C"))
    r.rounded_rect(w * 0.53, h * 0.78, w * 0.61, h * 0.91, 4,
                   color("#D08B4C"))
    r.ellipse(w * 0.43, h * 0.90, w * 0.045, h * 0.018, color("#FFF4E3"))
    r.ellipse(w * 0.57, h * 0.90, w * 0.045, h * 0.018, color("#FFF4E3"))

    # Body and white chest.
    r.ellipse(w * 0.50, h * 0.755, w * 0.19, h * 0.105, color("#D99856"))
    r.ellipse(w * 0.50, h * 0.79, w * 0.105, h * 0.065, color("#FFF4E3"))

    # Head, ears, blaze.
    r.circle(w * 0.50, h * 0.595, h * 0.128, color("#D99856"))
    r.polygon([(w * 0.385, h * 0.575), (w * 0.335, h * 0.465),
               (w * 0.455, h * 0.532)], color("#C57C40"))
    r.polygon([(w * 0.615, h * 0.575), (w * 0.665, h * 0.465),
               (w * 0.545, h * 0.532)], color("#C57C40"))
    r.polygon([(w * 0.397, h * 0.552), (w * 0.362, h * 0.492),
               (w * 0.442, h * 0.532)], color("#E9A9A2"))
    r.polygon([(w * 0.603, h * 0.552), (w * 0.638, h * 0.492),
               (w * 0.558, h * 0.532)], color("#E9A9A2"))
    r.polygon([(w * 0.462, h * 0.505), (w * 0.538, h * 0.505),
               (w * 0.516, h * 0.612), (w * 0.484, h * 0.612)],
              color("#FFF4E3"), 0.92)

    # Muzzle, eyes, nose, mouth, tongue.
    r.ellipse(w * 0.455, h * 0.652, w * 0.055, h * 0.043, color("#FFF4E3"))
    r.ellipse(w * 0.545, h * 0.652, w * 0.055, h * 0.043, color("#FFF4E3"))
    r.circle(w * 0.44, h * 0.592, 2.1, color("#2B2118"))
    r.circle(w * 0.56, h * 0.592, 2.1, color("#2B2118"))
    r.circle(w * 0.447, h * 0.586, 0.65, WHITE)
    r.circle(w * 0.567, h * 0.586, 0.65, WHITE)
    r.ellipse(w * 0.50, h * 0.632, 3.3, 2.3, color("#2B2118"))
    r.line(w * 0.50, h * 0.64, w * 0.50, h * 0.655, 0.9, color("#2B2118"))
    r.ellipse(w * 0.50, h * 0.672, 3.2, 4.0, color("#E77F8C"))
    r.line(w * 0.50, h * 0.655, w * 0.475, h * 0.668, 0.8,
           color("#2B2118"), 0.8)
    r.line(w * 0.50, h * 0.655, w * 0.525, h * 0.668, 0.8,
           color("#2B2118"), 0.8)

    # Flowers and grass in front of the paws.
    flower_rng = random.Random(5)
    for _ in range(18):
        x = flower_rng.uniform(w * 0.03, w * 0.97)
        y = flower_rng.uniform(h * 0.82, h * 0.98)
        if flower_rng.random() < 0.55:
            petal = WHITE
        else:
            petal = color("#F7D6DE")
        for angle in range(0, 360, 90):
            dx = 1.5 * math.cos(math.radians(angle))
            dy = 1.5 * math.sin(math.radians(angle))
            r.circle(x + dx, y + dy, 1.15, petal, 0.95)
        r.circle(x, y, 0.8, color("#F2C14E"), 0.95)

    r.vignette(0.14)


def cover_hike(r: Raster) -> None:
    w, h = r.w, r.h
    r.vertical_gradient(0, h, color("#9FC8E5"), color("#F4E6CF"))

    r.circle(w * 0.73, h * 0.20, h * 0.09, color("#FFD98B"), 0.22)
    r.circle(w * 0.73, h * 0.20, h * 0.055, color("#FFD98B"), 0.95)
    r.ellipse(w * 0.18, h * 0.20, w * 0.10, h * 0.028, WHITE, 0.72)
    r.ellipse(w * 0.40, h * 0.15, w * 0.12, h * 0.033, WHITE, 0.55)

    # Back range with snow.
    r.polygon([(0, h * 0.66), (w * 0.16, h * 0.40), (w * 0.34, h * 0.62),
               (w * 0.55, h * 0.32), (w * 0.75, h * 0.60),
               (w * 0.90, h * 0.44), (w, h * 0.60), (w, h * 0.78), (0, h * 0.78)],
              color("#8FA8B8"))
    r.polygon([(w * 0.05, h * 0.52), (w * 0.16, h * 0.40),
               (w * 0.27, h * 0.51), (w * 0.22, h * 0.50),
               (w * 0.19, h * 0.55), (w * 0.14, h * 0.48),
               (w * 0.10, h * 0.58)], color("#F7F4EE"), 0.92)
    r.polygon([(w * 0.46, h * 0.47), (w * 0.55, h * 0.32),
               (w * 0.65, h * 0.48), (w * 0.60, h * 0.46),
               (w * 0.56, h * 0.52), (w * 0.52, h * 0.44),
               (w * 0.49, h * 0.54)], color("#F7F4EE"), 0.92)

    # Front range with a shaded flank.
    r.polygon([(0, h * 0.82), (w * 0.22, h * 0.50), (w * 0.44, h * 0.78),
               (w * 0.64, h * 0.46), (w * 0.86, h * 0.76),
               (w, h * 0.58), (w, h * 0.88), (0, h * 0.88)],
              color("#5E7887"))
    r.polygon([(w * 0.64, h * 0.46), (w * 0.86, h * 0.76),
               (w, h * 0.58), (w, h * 0.88), (w * 0.58, h * 0.88)],
              color("#4C6472"), 0.75)

    # Foreground ridge.
    r.polygon([(0, h * 0.78), (w * 0.20, h * 0.72), (w * 0.42, h * 0.80),
               (w * 0.68, h * 0.73), (w, h * 0.80), (w, h), (0, h)],
              color("#41664B"))
    rng = random.Random(21)
    for _ in range(110):
        x = rng.uniform(0, w)
        y = rng.uniform(h * 0.80, h)
        r.line(x, y, x + rng.uniform(-2, 2), y - rng.uniform(2, 7),
               0.8, color("#5A7D5D"), 0.55)

    # Tent.
    r.polygon([(w * 0.06, h * 0.90), (w * 0.24, h * 0.90),
               (w * 0.15, h * 0.74)], color("#D9773E"))
    r.polygon([(w * 0.13, h * 0.90), (w * 0.15, h * 0.76),
               (w * 0.20, h * 0.90)], color("#8E4326"), 0.9)
    r.line(w * 0.15, h * 0.74, w * 0.06, h * 0.90, 0.6,
           color("#E8D8BD"), 0.8)

    # Three hikers on the ridge.
    for cx, cy, jacket in ((w * 0.55, h * 0.795, "#D9524A"),
                           (w * 0.64, h * 0.785, "#E7B84B"),
                           (w * 0.73, h * 0.80, "#3E7F70")):
        r.rounded_rect(cx - 2.4, cy, cx + 2.4, cy + 8.0, 2.2,
                       color(jacket))
        r.circle(cx, cy - 2.2, 2.1, color("#E3B18B"))
        r.rounded_rect(cx - 3.4, cy + 1.0, cx - 1.0, cy + 6.5, 1.2,
                       color("#404A4E"), 0.9)
        r.line(cx - 1.4, cy + 8.0, cx - 2.6, cy + 11.0, 1.2,
               color("#37424B"))
        r.line(cx + 1.4, cy + 8.0, cx + 2.6, cy + 11.0, 1.2,
               color("#37424B"))

    r.vignette(0.13)


def _card_layers(r: Raster, cx: float, cy: float, cw: float, ch: float,
                 angle: float, border: str, paper: str) -> None:
    outer = rotated_rect(cx, cy, cw, ch, angle)
    shadow = [(x + 2.0, y + 2.6) for x, y in outer]
    r.polygon(shadow, color("#2A0C0F"), 0.38)
    r.polygon(outer, color(border))
    inner = rotated_rect(cx, cy, cw * 0.88, ch * 0.84, angle)
    r.polygon(inner, color(paper))
    ink = color("#9A3B40")
    for line_index in range(3):
        offset = (line_index - 1) * ch * 0.17
        half = cw * (0.30 if line_index != 2 else 0.20)
        a = rotate(cx - half, cy + offset, cx, cy, angle)
        b = rotate(cx + half, cy + offset, cx, cy, angle)
        r.line(a[0], a[1], b[0], b[1], 1.2, ink, 0.55)
    # A tiny illustration block inside the card.
    block = rotate(cx, cy - ch * 0.28, cx, cy, angle)
    r.circle(block[0], block[1], min(cw, ch) * 0.09, ink, 0.45)


def cover_cards(r: Raster) -> None:
    w, h = r.w, r.h
    r.vertical_gradient(0, h, color("#3A171B"), color("#5C2127"))
    r.radial_glow(w * 0.42, h * 0.35, w * 0.62, color("#A63D46"), 0.42)
    rng = random.Random(31)
    for _ in range(28):
        r.circle(rng.uniform(0, w), rng.uniform(0, h),
                 rng.uniform(0.5, 1.4), color("#F0C9A8"), 0.10)

    cards = [
        (w * 0.30, h * 0.31, w * 0.37, h * 0.34, -13.0),
        (w * 0.65, h * 0.29, w * 0.34, h * 0.31, 8.0),
        (w * 0.22, h * 0.68, w * 0.39, h * 0.31, 7.0),
        (w * 0.62, h * 0.67, w * 0.35, h * 0.33, -10.0),
    ]
    for index, (cx, cy, cw, ch, angle) in enumerate(cards):
        paper = "#F4E5D0" if index % 2 == 0 else "#EEDBC1"
        _card_layers(r, cx, cy, cw, ch, angle, "#8E2F36", paper)

    # Tape strips.
    for cx, cy, cw, ch, angle in (
            (w * 0.20, h * 0.18, w * 0.13, h * 0.035, -13.0),
            (w * 0.74, h * 0.46, w * 0.11, h * 0.032, 8.0)):
        r.polygon(rotated_rect(cx, cy, cw, ch, angle), WHITE, 0.45)

    # A coin/sticker near the top right.
    r.circle(w * 0.82, h * 0.14, 7.0, color("#C9963E"))
    r.circle(w * 0.82, h * 0.14, 5.2, color("#E7BD63"))
    r.circle(w * 0.82, h * 0.14, 2.0, color("#8E2F36"), 0.8)

    r.vignette(0.30)


def cover_tennis(r: Raster) -> None:
    w, h = r.w, r.h
    r.vertical_gradient(0, h, color("#7FA889"), color("#3F6B4E"))

    rng = random.Random(41)
    for _ in range(70):
        x = rng.uniform(0, w)
        y = rng.uniform(0, h * 0.34)
        radius = rng.uniform(3, 12)
        shade = "#5E8B65" if rng.random() < 0.5 else "#94B98C"
        r.circle(x, y, radius, color(shade), 0.35)

    # Court.
    r.polygon([(w * 0.05, h * 0.34), (w * 0.95, h * 0.34),
               (w, h), (0, h)], color("#4F8D63"))
    white = color("#E9F1E7")
    for a, b in (
            ((0.07, 0.36), (0.01, 0.99)),
            ((0.93, 0.36), (0.99, 0.99)),
            ((0.18, 0.36), (0.10, 0.99)),
            ((0.82, 0.36), (0.90, 0.99)),
            ((0.07, 0.64), (0.93, 0.64)),
            ((0.12, 0.82), (0.88, 0.82)),
            ((0.50, 0.36), (0.50, 0.99)),
            ((0.18, 0.82), (0.82, 0.82))):
        r.line(a[0] * w, a[1] * h, b[0] * w, b[1] * h, 1.0, white, 0.72)

    # Net.
    net_y = h * 0.64
    r.line(0, net_y, w, net_y, 1.6, color("#ECF0EA"), 0.85)
    for x in range(0, w + 1, 6):
        r.line(x, net_y - h * 0.035, x, net_y + h * 0.035, 0.55,
               color("#ECF0EA"), 0.35)
    r.rounded_rect(w * 0.02, net_y - h * 0.055, w * 0.045, net_y + h * 0.06,
                   1.2, color("#374C3A"))
    r.rounded_rect(w * 0.955, net_y - h * 0.055, w * 0.98, net_y + h * 0.06,
                   1.2, color("#374C3A"))

    # Player, mid-serve.
    navy = color("#1C2A3A")
    skin = color("#E1AE88")
    r.ellipse(w * 0.50, h * 0.72, w * 0.17, h * 0.035, color("#254127"), 0.30)
    r.circle(w * 0.455, h * 0.255, 5.2, skin)
    r.line(w * 0.47, h * 0.30, w * 0.515, h * 0.47, 9.0, navy)
    r.line(w * 0.50, h * 0.45, w * 0.41, h * 0.60, 4.5, navy)
    r.line(w * 0.50, h * 0.45, w * 0.59, h * 0.61, 4.5, navy)
    r.ellipse(w * 0.39, h * 0.615, 5.0, 2.2, WHITE)
    r.ellipse(w * 0.61, h * 0.625, 5.0, 2.2, WHITE)
    r.line(w * 0.48, h * 0.33, w * 0.37, h * 0.28, 3.4, skin)
    r.line(w * 0.49, h * 0.33, w * 0.59, h * 0.20, 3.4, skin)
    r.line(w * 0.59, h * 0.20, w * 0.65, h * 0.105, 1.6,
           color("#DDE2E6"))
    racket_cx, racket_cy = w * 0.665, h * 0.095
    r.circle(racket_cx, racket_cy, 8.0, color("#E8ECEF"), 0.22)
    r.circle(racket_cx, racket_cy, 7.2, WHITE, 0.30)
    for dy in (-4, 0, 4):
        r.line(racket_cx - 5, racket_cy + dy, racket_cx + 5,
               racket_cy + dy, 0.35, color("#E8ECEF"), 0.45)
    # Ball.
    r.circle(w * 0.82, h * 0.17, 3.0, color("#E6E14E"))
    r.line(w * 0.86, h * 0.14, w * 0.92, h * 0.10, 0.8, WHITE, 0.45)
    r.line(w * 0.87, h * 0.17, w * 0.94, h * 0.14, 0.8, WHITE, 0.35)

    r.vignette(0.16)


def cover_dessert(r: Raster) -> None:
    w, h = r.w, r.h
    r.vertical_gradient(0, h, color("#F3E4CE"), color("#E5CDB0"))
    rng = random.Random(51)
    for _ in range(22):
        r.circle(rng.uniform(0, w), rng.uniform(0, h * 0.55),
                 rng.uniform(3, 10), color("#FFF6E8"), 0.22)
    r.vertical_gradient(h * 0.62, h, color("#E7D0B2"), color("#D9BE9C"))

    r.ellipse(w * 0.50, h * 0.84, w * 0.42, h * 0.055, color("#8A5E3F"), 0.24)
    r.ellipse(w * 0.50, h * 0.80, w * 0.40, h * 0.055, color("#FBF7F0"))
    r.ellipse(w * 0.50, h * 0.79, w * 0.35, h * 0.043, color("#F0E9DD"), 0.6)

    # Ramekin.
    r.polygon([(w * 0.30, h * 0.50), (w * 0.70, h * 0.50),
               (w * 0.64, h * 0.79), (w * 0.36, h * 0.79)],
              color("#FAF6EF"))
    r.polygon([(w * 0.64, h * 0.79), (w * 0.70, h * 0.50),
               (w * 0.70, h * 0.78)], color("#E8DDCB"), 0.6)
    r.ellipse(w * 0.50, h * 0.50, w * 0.20, h * 0.055, color("#FFFDF9"))
    r.ellipse(w * 0.50, h * 0.505, w * 0.17, h * 0.042,
              color("#C97B3C"))
    r.ellipse(w * 0.46, h * 0.495, w * 0.075, h * 0.018,
              color("#E2A05F"), 0.75)
    for x, y, rx in ((w * 0.37, h * 0.515, w * 0.05),
                     (w * 0.57, h * 0.535, w * 0.045),
                     (w * 0.62, h * 0.51, w * 0.03)):
        r.ellipse(x, y, rx, h * 0.012, color("#A95F2C"), 0.75)

    # Sugar crystals.
    for _ in range(16):
        x = rng.uniform(w * 0.36, w * 0.64)
        y = rng.uniform(h * 0.495, h * 0.535)
        r.circle(x, y, 0.55, color("#F6D7A9"), 0.9)

    # Mint leaves.
    for cx, cy, angle in ((w * 0.40, h * 0.45, -35),
                          (w * 0.44, h * 0.44, 20),
                          (w * 0.48, h * 0.455, 65)):
        pts = rotated_rect(cx, cy, 7.5, 3.4, angle)
        r.polygon(pts, color("#5E8F55"), 0.95)

    # Red berries.
    for cx, cy in ((w * 0.58, h * 0.455), (w * 0.61, h * 0.47),
                   (w * 0.55, h * 0.47)):
        r.circle(cx, cy, 2.1, color("#B93A3A"))
        r.circle(cx - 0.5, cy - 0.6, 0.55, WHITE, 0.6)

    # Spoon.
    r.line(w * 0.79, h * 0.73, w * 0.94, h * 0.55, 3.2,
           color("#C9CED3"))
    r.ellipse(w * 0.945, h * 0.535, w * 0.050, h * 0.050,
              color("#D7DBDF"))
    r.ellipse(w * 0.945, h * 0.535, w * 0.036, h * 0.036,
              color("#B9BFC5"), 0.55)

    r.vignette(0.12)


def cover_outfit(r: Raster) -> None:
    w, h = r.w, r.h
    r.vertical_gradient(0, h, color("#F1E8DB"), color("#E7DBCB"))

    r.ellipse(w * 0.50, h * 0.92, w * 0.40, h * 0.05, color("#B79F83"), 0.25)

    cream = color("#F5ECDE")
    crease = color("#E2D4C0")
    camel = color("#B98D60")

    # Sweater body and sleeves.
    r.rounded_rect(w * 0.28, h * 0.14, w * 0.68, h * 0.58, 12, cream)
    r.line(w * 0.31, h * 0.20, w * 0.20, h * 0.42, 10, cream)
    r.line(w * 0.65, h * 0.20, w * 0.77, h * 0.42, 10, cream)
    r.ellipse(w * 0.48, h * 0.145, w * 0.10, h * 0.028, crease, 0.9)
    r.ellipse(w * 0.48, h * 0.155, w * 0.065, h * 0.018, color("#D8C7B0"))
    for y in (h * 0.50, h * 0.52, h * 0.54):
        r.line(w * 0.31, y, w * 0.65, y, 0.7, crease, 0.8)

    # Trousers.
    r.rounded_rect(w * 0.32, h * 0.60, w * 0.48, h * 0.93, 5, camel)
    r.rounded_rect(w * 0.50, h * 0.60, w * 0.66, h * 0.93, 5, camel)
    r.rounded_rect(w * 0.32, h * 0.585, w * 0.66, h * 0.625, 3,
                   color("#A87D51"))
    r.line(w * 0.40, h * 0.63, w * 0.40, h * 0.90, 0.7,
           color("#C9A177"), 0.8)
    r.line(w * 0.58, h * 0.63, w * 0.58, h * 0.90, 0.7,
           color("#C9A177"), 0.8)

    # Shoes.
    r.ellipse(w * 0.39, h * 0.94, w * 0.095, h * 0.035,
              color("#FBF8F2"))
    r.ellipse(w * 0.59, h * 0.94, w * 0.095, h * 0.035,
              color("#FBF8F2"))
    r.ellipse(w * 0.39, h * 0.955, w * 0.085, h * 0.015,
              color("#D8C9B4"), 0.8)
    r.ellipse(w * 0.59, h * 0.955, w * 0.085, h * 0.015,
              color("#D8C9B4"), 0.8)

    # Bag.
    r.rounded_rect(w * 0.71, h * 0.63, w * 0.90, h * 0.82, 5,
                   color("#C44B3F"))
    r.line(w * 0.74, h * 0.63, w * 0.80, h * 0.50, 1.4,
           color("#8E342D"))
    r.line(w * 0.87, h * 0.63, w * 0.81, h * 0.50, 1.4,
           color("#8E342D"))
    r.rounded_rect(w * 0.785, h * 0.70, w * 0.825, h * 0.725, 1.5,
                   color("#E7C46A"))

    # Sunglasses.
    r.circle(w * 0.11, h * 0.20, 6.0, color("#25262B"))
    r.circle(w * 0.22, h * 0.20, 6.0, color("#25262B"))
    r.line(w * 0.17, h * 0.19, w * 0.18, h * 0.19, 1.2,
           color("#25262B"))
    r.circle(w * 0.105, h * 0.185, 2.0, color("#6E747C"), 0.45)
    r.circle(w * 0.215, h * 0.185, 2.0, color("#6E747C"), 0.45)

    # Plant sprig.
    r.line(w * 0.90, h * 0.10, w * 0.96, h * 0.24, 1.2,
           color("#5C7F55"))
    for cx, cy, angle in ((w * 0.925, h * 0.145, 35),
                          (w * 0.945, h * 0.19, 15),
                          (w * 0.905, h * 0.19, -25)):
        pts = rotated_rect(cx, cy, 5.5, 2.4, angle)
        r.polygon(pts, color("#6E9560"), 0.95)

    r.vignette(0.10)


# ---------------------------------------------------------------------------
# Icons (RGBA, drawn at 4x)
# ---------------------------------------------------------------------------


def icon_search() -> Raster:
    r = Raster(20, 20, 4)
    ink = color("#1C1C1E")
    _ring(r, 9.2, 8.8, 5.9, 1.7, ink)
    r.line(13.4, 13.0, 17.4, 17.0, 2.0, ink)
    return r


def _ring(r: Raster, cx: float, cy: float, radius: float, width: float,
          ink: tuple[float, float, float], alpha: float = 1.0) -> None:
    s = r.s
    scx, scy = cx * s, cy * s
    sr = radius * s
    half = width * s / 2.0
    left, top, right, bottom = r._bounds(cx - radius - width,
                                         cy - radius - width,
                                         cx + radius + width,
                                         cy + radius + width)
    for y in range(top, bottom):
        dy = (y + 0.5) - scy
        for x in range(left, right):
            distance = math.hypot((x + 0.5) - scx, dy)
            coverage = clamp(0.5 + half - abs(distance - sr))
            if coverage > 0.0:
                r.blend(x, y, ink, alpha * coverage)


def icon_heart(filled: bool) -> Raster:
    r = Raster(14, 14, 4)
    ink = color("#FF2442") if filled else color("#8E8E93")
    cx, cy, radius = 7.0, 6.6, 5.5

    def inside(px: float, py: float, scale: float) -> bool:
        nx = (px - cx) / (radius * scale)
        ny = (cy - py) / (radius * scale) + 0.10
        value = (nx * nx + ny * ny - 1.0) ** 3 - nx * nx * ny ** 3
        return value < 0.0

    s = r.s
    for y in range(-2 * s, 15 * s):
        for x in range(-2 * s, 16 * s):
            px = (x + 0.5) / s
            py = (y + 0.5) / s
            if inside(px, py, 1.0) and (filled or not inside(px, py, 0.80)):
                r.blend(x, y, ink, 1.0)
    return r


def icon_chevron() -> Raster:
    r = Raster(12, 12, 4)
    ink = color("#8E8E93")
    r.line(3.0, 4.2, 6.0, 7.4, 1.6, ink)
    r.line(6.0, 7.4, 9.0, 4.2, 1.6, ink)
    return r


def icon_plus() -> Raster:
    r = Raster(14, 14, 4)
    r.line(7.0, 2.2, 7.0, 11.8, 2.2, WHITE)
    r.line(2.2, 7.0, 11.8, 7.0, 2.2, WHITE)
    return r


def icon_signal() -> Raster:
    r = Raster(16, 10, 4)
    ink = color("#111113")
    for index, height in enumerate((4, 6, 8, 10)):
        x = 0.5 + index * 4.0
        r.rounded_rect(x, 10.0 - height, x + 2.6, 10.0, 1.0, ink)
    return r


def icon_wifi() -> Raster:
    r = Raster(15, 10, 4)
    ink = color("#111113")
    cx, cy = 7.5, 8.6
    for radius, width in ((7.4, 1.3), (5.0, 1.3), (2.6, 1.3)):
        s = r.s
        half = width * s / 2.0
        sr = radius * s
        scx, scy = cx * s, cy * s
        for y in range(0, r.H):
            dy = (y + 0.5) - scy
            for x in range(0, r.W):
                dx = (x + 0.5) - scx
                distance = math.hypot(dx, dy)
                if abs(distance - sr) <= half:
                    angle = math.degrees(math.atan2(abs(dx), -dy))
                    if angle <= 52.0:
                        r.blend(x, y, ink, 1.0 - abs(distance - sr) / half * 0.15)
    r.circle(cx, cy, 1.2, ink)
    return r


def icon_battery() -> Raster:
    r = Raster(22, 11, 4)
    ink = color("#111113")
    r.rounded_rect(0.7, 0.9, 19.8, 10.1, 2.6, ink)
    # Hollow body: draw the border as four thin capsules, then refill the inner
    # area with white and the charge level with ink.
    r.rounded_rect(2.0, 2.2, 18.4, 8.8, 1.8, WHITE)
    r.rounded_rect(2.0, 2.2, 14.9, 8.8, 1.8, ink)
    r.rounded_rect(20.1, 3.6, 21.6, 7.4, 1.2, ink)
    return r


def icon_play_badge() -> Raster:
    r = Raster(22, 22, 4)
    r.circle(11.0, 11.0, 10.0, color("#000000"), 0.38)
    r.polygon([(8.7, 6.8), (8.7, 15.2), (15.6, 11.0)], WHITE, 0.92)
    return r


def icon_back() -> Raster:
    r = Raster(16, 16, 4)
    ink = color("#1C1C1E")
    r.line(10.4, 3.2, 5.4, 8.0, 1.8, ink)
    r.line(5.4, 8.0, 10.4, 12.8, 1.8, ink)
    return r


def icon_more() -> Raster:
    r = Raster(18, 6, 4)
    ink = color("#1C1C1E")
    for cx in (3.0, 9.0, 15.0):
        r.circle(cx, 3.0, 1.3, ink)
    return r


def icon_comment() -> Raster:
    r = Raster(16, 16, 4)
    ink = color("#5A5A5F")
    r.rounded_rect(1.6, 2.2, 14.4, 11.4, 3.0, ink)
    r.polygon([(4.2, 10.6), (4.2, 14.6), (8.7, 11.4)], ink)
    return r


def star_points(cx: float, cy: float, outer: float,
                inner: float) -> list[tuple[float, float]]:
    points = []
    for index in range(10):
        radius = outer if index % 2 == 0 else inner
        angle = math.radians(-90 + index * 36)
        points.append((cx + radius * math.cos(angle),
                       cy + radius * math.sin(angle)))
    return points


def icon_star(filled: bool) -> Raster:
    r = Raster(16, 16, 4)
    ink = color("#F5B942") if filled else color("#8E8E93")
    r.polygon(star_points(8.0, 8.2, 6.8, 2.9), ink)
    return r


def icon_location() -> Raster:
    r = Raster(12, 14, 4)
    ink = color("#8A8A8E")
    r.circle(6.0, 5.2, 4.2, ink)
    r.polygon([(2.4, 7.2), (9.6, 7.2), (6.0, 13.4)], ink)
    r.circle(6.0, 5.2, 1.5, WHITE)
    return r


def icon_close() -> Raster:
    r = Raster(14, 14, 4)
    ink = color("#1C1C1E")
    r.line(3.2, 3.2, 10.8, 10.8, 1.8, ink)
    r.line(10.8, 3.2, 3.2, 10.8, 1.8, ink)
    return r


def icon_plane() -> Raster:
    r = Raster(16, 16, 4)
    ink = color("#3C7DF2")
    r.polygon([(1.5, 7.2), (14.5, 2.0), (10.2, 14.2), (7.6, 8.6)], ink)
    r.line(7.6, 8.6, 14.5, 2.0, 0.7, WHITE, 0.85)
    return r


def icon_check() -> Raster:
    r = Raster(20, 20, 4)
    ink = color("#34A853")
    r.line(3.6, 10.6, 8.0, 15.0, 2.4, ink)
    r.line(8.0, 15.0, 16.4, 5.2, 2.4, ink)
    return r


ICONS = {
    "search": (icon_search, 20, 20),
    "heart_outline": (lambda: icon_heart(False), 14, 14),
    "heart_filled": (lambda: icon_heart(True), 14, 14),
    "chevron_down": (icon_chevron, 12, 12),
    "plus": (icon_plus, 14, 14),
    "signal": (icon_signal, 16, 10),
    "wifi": (icon_wifi, 15, 10),
    "battery": (icon_battery, 22, 11),
    "play_badge": (icon_play_badge, 22, 22),
    "back": (icon_back, 16, 16),
    "more": (icon_more, 18, 6),
    "comment": (icon_comment, 16, 16),
    "star": (lambda: icon_star(False), 16, 16),
    "star_filled": (lambda: icon_star(True), 16, 16),
    "location": (icon_location, 12, 14),
    "close": (icon_close, 14, 14),
    "plane": (icon_plane, 16, 16),
    "check": (icon_check, 20, 20),
}

COVERS = [
    ("xhs_cover_0", 138, 170, cover_dog, 3),
    ("xhs_cover_1", 138, 150, cover_hike, 3),
    ("xhs_cover_2", 138, 160, cover_cards, 3),
    ("xhs_cover_3", 138, 150, cover_tennis, 3),
    ("xhs_cover_4", 138, 190, cover_dessert, 3),
    ("xhs_cover_5", 138, 140, cover_outfit, 3),
]


# ---------------------------------------------------------------------------
# C emission
# ---------------------------------------------------------------------------


def emit_texts() -> None:
    lines = [
        "/* Generated by gen_xhs_assets.py; do not edit by hand. */",
        "#ifndef XHS_TEXTS_H",
        "#define XHS_TEXTS_H",
        "",
    ]
    for key, value in TEXTS.items():
        lines.append(f'#define XHS_TXT_{key} "{value}"')
    lines += ["", "#endif /* XHS_TEXTS_H */", ""]
    (HERE / "xhs_texts.h").write_text("\n".join(lines), encoding="utf-8")


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


def emit_images(preview_dir: Path | None) -> None:
    lines = [
        "/* Generated by gen_xhs_assets.py; do not edit by hand. */",
        "#ifndef XHS_IMAGES_H",
        "#define XHS_IMAGES_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    preview_dir and preview_dir.mkdir(parents=True, exist_ok=True)

    for index, (name, width, height, draw, scale) in enumerate(COVERS):
        raster = Raster(width, height, scale)
        draw(raster)
        pixels = raster.rgb565(grain=2.6, seed=100 + index)
        if preview_dir:
            rgba = raster.rgba8(grain=2.6, seed=100 + index)
            write_png(preview_dir / f"{name}.png", width, height,
                      [(r, g, b) for r, g, b, _ in rgba])
        lines += [f"#define {name.upper()}_W {width}",
                  f"#define {name.upper()}_H {height}", ""]
        lines += _emit_u16(pixels, f"{name}_data")
        lines += [
            f"static const lv_image_dsc_t {name} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_RGB565,",
            "        .flags = 0,",
            f"        .w = {width},",
            f"        .h = {height},",
            f"        .stride = {width * 2},",
            "        .reserved_2 = 0,",
            "    },",
            f"    .data_size = sizeof({name}_data),",
            f"    .data = (const uint8_t *){name}_data,",
            "};",
            "",
        ]

    for key, (draw, width, height) in ICONS.items():
        raster = draw()
        rgba = raster.rgba8()
        values = [(a << 24) | (r << 16) | (g << 8) | b
                  for r, g, b, a in rgba]
        if preview_dir:
            flattened = []
            for red, green, blue, alpha in rgba:
                t = alpha / 255.0
                flattened.append((round(red * t + 255 * (1 - t)),
                                  round(green * t + 255 * (1 - t)),
                                  round(blue * t + 255 * (1 - t))))
            write_png(preview_dir / f"icon_{key}.png", width, height,
                      flattened)
        symbol = f"xhs_icon_{key}"
        lines += [f"#define {symbol.upper()}_W {width}",
                  f"#define {symbol.upper()}_H {height}", ""]
        lines += _emit_u32(values, f"{symbol}_data")
        lines += [
            f"static const lv_image_dsc_t {symbol} = {{",
            "    .header = {",
            "        .magic = LV_IMAGE_HEADER_MAGIC,",
            "        .cf = LV_COLOR_FORMAT_ARGB8888,",
            "        .flags = 0,",
            f"        .w = {width},",
            f"        .h = {height},",
            f"        .stride = {width * 4},",
            "        .reserved_2 = 0,",
            "    },",
            f"    .data_size = sizeof({symbol}_data),",
            f"    .data = (const uint8_t *){symbol}_data,",
            "};",
            "",
        ]

    lines += ["#endif /* XHS_IMAGES_H */", ""]
    (HERE / "xhs_images.h").write_text("\n".join(lines), encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONTS = [
    ("xhs_font_11", "regular", 11),
    ("xhs_font_12", "regular", 12),
    ("xhs_font_12b", "bold", 12),
    ("xhs_font_13", "regular", 13),
    ("xhs_font_14", "regular", 14),
    ("xhs_font_14b", "bold", 14),
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
    stamp = HERE / "xhs_fonts.sha256"
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
        # Keep the generated banner free of build-machine absolute paths.
        text = text.replace(str(HERE), ".")
        text = text.replace(str(source[weight]), Path(source[weight]).name)
        text = text.replace(f"const lv_font_t {name} =",
                            f"static const lv_font_t {name} =")
        # All generated fonts share the same internal table names. Prefix them
        # so several font headers can live in one translation unit. Only the
        # declarations and the initializers are touched; struct field names
        # such as .glyph_bitmap and .cmaps must stay intact.
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
            f"/* Generated by gen_xhs_assets.py from {source[weight].name};"
            " do not edit. */\n" + text)
        (HERE / f"{name}.h").write_text(header, encoding="utf-8")
        output.unlink()

    stamp.write_text(signature + "\n", encoding="utf-8")


def emit_aggregate() -> None:
    lines = [
        "/* Generated by gen_xhs_assets.py; do not edit by hand. */",
        "#ifndef XHS_ASSETS_H",
        "#define XHS_ASSETS_H",
        "",
        '#include "lvgl.h"',
        "",
    ]
    for name, _, _ in FONTS:
        lines.append(f'#include "{name}.h"')
    lines += ['#include "xhs_images.h"', "", "#endif /* XHS_ASSETS_H */", ""]
    (HERE / "xhs_assets.h").write_text("\n".join(lines), encoding="utf-8")


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
