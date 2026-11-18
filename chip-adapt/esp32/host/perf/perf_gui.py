"""Desktop control panel for the PERF TAPE monitor.

This is a tkinter client for the ESP32 host's local HTTP API.  It never opens
a COM port: frames and layout commands still go through ``host.py`` and its
``SerialBroker``, so the host remains the only serial owner.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Optional

PERF_DIR = Path(__file__).resolve().parent
HOST_DIR = PERF_DIR.parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from tray import TrayIcon  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:8767"
POLL_MS = 300

BG = "#080705"
PANEL = "#0d0b08"
PANEL_2 = "#12100c"
STATUS_BG = "#0e0b07"
TAPE = "#0d0a07"
INK = "#efe7d3"
MUTED = "#978d78"
DIM = "#6b6250"
LINE = "#2a241a"
LINE_SOFT = "#1a1710"
ACCENT = "#ff5a2c"
WARN = "#f0b347"
OK = "#b7c48a"
ERR_TEXT = "#e7a08a"


class HostError(RuntimeError):
    """A local host request failed or returned an error payload."""


class HostClient:
    """Small JSON client for the already-running ESP32 host."""

    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = normalize_url(base_url)
        self.timeout = timeout

    def _request(
        self,
        path: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout if timeout is None else timeout,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            message = http_error_message(exc)
            raise HostError(message) from exc
        except urllib.error.URLError as exc:
            raise HostError(f"host unreachable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise HostError("host request timed out") from exc
        try:
            result = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as exc:
            raise HostError("host returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise HostError("host returned a non-object payload")
        if result.get("ok") is False:
            message = result.get("message") or result.get("error")
            raise HostError(str(message or "host request failed"))
        return result

    def status(self) -> dict[str, Any]:
        return self._request("/api/perf/status")

    def serial_status(self) -> dict[str, Any]:
        return self._request("/api/status")

    def start(
        self, mode: str, interval: float, layout: str
    ) -> dict[str, Any]:
        return self._request(
            "/api/perf/start",
            {"mode": mode, "interval": interval, "layout": layout},
        )

    def stop(self) -> dict[str, Any]:
        return self._request("/api/perf/stop", {})

    def set_layout(self, layout: str) -> dict[str, Any]:
        return self._request("/api/perf/layout", {"layout": layout})

    def close_link(self, timeout: float = 2.0) -> dict[str, Any]:
        return self._request("/api/close", {}, timeout=timeout)


def normalize_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        value = DEFAULT_URL
    if "://" not in value:
        value = "http://" + value
    return value


def http_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # pragma: no cover - best effort only
        body = ""
    try:
        payload = json.loads(body)
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
    return f"HTTP {exc.code} {exc.reason}".strip()


class ScreenPainter:
    """Draw in 172x320 / 320x172 screen coordinates."""

    def __init__(
        self,
        canvas: tk.Canvas,
        ox: float,
        oy: float,
        scale: float,
        font_factory: Callable[[str, int, bool], tkfont.Font],
        mono: str,
    ) -> None:
        self.canvas = canvas
        self.ox = ox
        self.oy = oy
        self.scale = scale
        self.font_factory = font_factory
        self.mono = mono

    def x(self, value: float) -> float:
        return self.ox + value * self.scale

    def y(self, value: float) -> float:
        return self.oy + value * self.scale

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: str,
        outline: str = "",
    ) -> None:
        self.canvas.create_rectangle(
            self.x(x),
            self.y(y),
            self.x(x + w),
            self.y(y + h),
            fill=color,
            outline=outline,
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str,
        width: float = 1.0,
        dash: Optional[tuple[int, int]] = None,
    ) -> None:
        self.canvas.create_line(
            self.x(x1),
            self.y(y1),
            self.x(x2),
            self.y(y2),
            fill=color,
            width=max(1, int(round(width * self.scale))),
            dash=dash,
        )

    def polygon(self, points: list[tuple[float, float]], color: str) -> None:
        coords: list[float] = []
        for px, py in points:
            coords.extend((self.x(px), self.y(py)))
        self.canvas.create_polygon(
            coords, fill=color, outline="", splinesteps=1
        )

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float,
        color: str,
        family: Optional[str] = None,
        anchor: str = "nw",
        bold: bool = False,
    ) -> None:
        self.canvas.create_text(
            self.x(x),
            self.y(y),
            text=value,
            fill=color,
            anchor=anchor,
            font=self.font_factory(family or self.mono, int(size), bold),
        )

    def measure(
        self,
        value: str,
        size: float,
        family: Optional[str] = None,
        bold: bool = False,
    ) -> float:
        font = self.font_factory(family or self.mono, int(size), bold)
        return font.measure(value) / self.scale


class PerfGui:
    def __init__(
        self, root: tk.Tk, client: HostClient, *, tray_enabled: bool = True
    ) -> None:
        self.root = root
        self.client = client
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.tray_enabled = tray_enabled
        self.tray: Optional[TrayIcon] = None
        self.tray_events: queue.Queue[str] = queue.Queue()
        self.closing = False
        self.poll_inflight = False
        self.poll_token = 0
        self.busy = False
        self.initialized = False
        self.host_seen = False
        self.mode = "demo"
        self.interval = 0.3
        self.layout = "portrait"
        self.running = False
        self.last_perf: Optional[dict[str, Any]] = None
        self.last_error = ""
        self.last_poll_error = ""
        self.last_seq: Optional[int] = None
        self.cpu_history: list[int] = []
        self.down_history: list[int] = []
        self.up_history: list[int] = []
        self.fonts: dict[tuple[str, int, bool], tkfont.Font] = {}
        self.ui_fonts: dict[tuple[str, int, bool], tkfont.Font] = {}
        self.poll_after: Optional[str] = None
        self.drain_after: Optional[str] = None
        self.resize_after: Optional[str] = None

        self.mono = self.pick_font(
            "Cascadia Mono", "Consolas", "Courier New"
        )
        self.cond = self.pick_font(
            "Bahnschrift SemiCondensed", "Bahnschrift", "Arial Narrow",
            "Segoe UI",
        )
        self.sans = self.pick_font(
            "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"
        )

        self.mode_var = tk.StringVar(value=self.mode)
        self.interval_var = tk.StringVar(value=f"{self.interval:.1f}")
        self.error_var = tk.StringVar(value="")
        self.run_state_var = tk.StringVar(value="IDLE")
        self.serial_var = tk.StringVar(value="HOST · CONNECTING")
        self.dims_var = tk.StringVar(value="172 × 320")
        self.stat_vars = {
            "period": tk.StringVar(value="--"),
            "last": tk.StringVar(value="--"),
            "threads": tk.StringVar(value="--"),
            "seq": tk.StringVar(value="--"),
        }

        self.build_window()
        self.set_layout_ui(self.layout)
        self.update_controls()
        self.append_log("python gui ready", "dim")
        self.append_log(f"host {self.client.base_url}", "dim")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.drain_after = self.root.after(80, self.drain_events)
        self.root.after(120, self.poll)
        if self.tray_enabled:
            self.root.after(200, self.start_tray)

    # ------------------------------------------------------------------
    # window
    # ------------------------------------------------------------------

    def pick_font(self, *candidates: str) -> str:
        families = set(tkfont.families(self.root))
        for name in candidates:
            if name in families:
                return name
        return candidates[-1]

    def font(
        self, family: str, size: int, bold: bool = False
    ) -> tkfont.Font:
        key = (family, size, bold)
        font = self.fonts.get(key)
        if font is None:
            font = tkfont.Font(
                family=family,
                size=-max(6, size),
                weight="bold" if bold else "normal",
            )
            self.fonts[key] = font
        return font

    def ui_font(
        self, family: str, size: int, bold: bool = False
    ) -> tkfont.Font:
        key = (family, size, bold)
        font = self.ui_fonts.get(key)
        if font is None:
            font = tkfont.Font(
                family=family,
                size=size,
                weight="bold" if bold else "normal",
            )
            self.ui_fonts[key] = font
        return font

    def panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PANEL,
            bd=0,
            highlightbackground=LINE_SOFT,
            highlightthickness=1,
        )

    def panel_head(
        self, parent: tk.Widget, title: str, right: Optional[tk.Widget] = None
    ) -> tk.Frame:
        head = tk.Frame(parent, bg=PANEL, height=32)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(
            head,
            text=title,
            bg=PANEL,
            fg=MUTED,
            font=self.ui_font(self.mono, 8),
            anchor="w",
        ).pack(side="left", padx=12)
        if right is not None:
            right.pack(side="right", padx=12)
        tk.Frame(parent, bg=LINE_SOFT, height=1).pack(fill="x")
        return head

    def build_window(self) -> None:
        self.root.title("PERF TAPE · Python GUI")
        self.root.configure(bg=BG)
        self.root.geometry("1160x800")
        self.root.minsize(1020, 720)

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=22, pady=(18, 12))

        mark = tk.Canvas(
            header, width=10, height=10, bg=BG, highlightthickness=0
        )
        mark.create_rectangle(0, 0, 10, 10, fill=ACCENT, outline="")
        mark.pack(side="left", pady=(5, 0))

        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left", padx=(10, 0))
        tk.Label(
            brand,
            text="PERF TAPE",
            bg=BG,
            fg=INK,
            font=self.ui_font(self.cond, 18, True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="PYTHON GUI / ESP32-C6",
            bg=BG,
            fg=DIM,
            font=self.ui_font(self.mono, 7),
            anchor="w",
        ).pack(anchor="w")

        web_button = tk.Button(
            header,
            text="WEB UI ↗",
            command=self.open_web,
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=ACCENT,
            bd=0,
            highlightthickness=0,
            font=self.ui_font(self.mono, 8),
            cursor="hand2",
            takefocus=False,
        )
        web_button.pack(side="right")

        serial_box = tk.Frame(header, bg=BG)
        serial_box.pack(side="right", padx=(12, 0))
        self.serial_dot = tk.Canvas(
            serial_box, width=8, height=8, bg=BG, highlightthickness=0
        )
        self.serial_dot.pack(side="left")
        self.serial_dot.create_oval(1, 1, 7, 7, fill=DIM, outline="")
        tk.Label(
            serial_box,
            textvariable=self.serial_var,
            bg=BG,
            fg=MUTED,
            font=self.ui_font(self.mono, 8),
        ).pack(side="left", padx=(7, 0))

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        main.grid_columnconfigure(0, weight=1, minsize=560)
        main.grid_columnconfigure(1, weight=0, minsize=382)
        main.grid_rowconfigure(0, weight=1)

        self.build_preview(main)
        self.build_side(main)

    def build_preview(self, parent: tk.Frame) -> None:
        panel = self.panel(parent)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))

        dims = tk.Label(
            panel,
            textvariable=self.dims_var,
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.mono, 8),
        )
        self.panel_head(panel, "DEVICE / PREVIEW", dims)

        self.canvas = tk.Canvas(
            panel, bg=BG, highlightthickness=0, width=560, height=560
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        foot = tk.Frame(panel, bg=PANEL, height=26)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        tk.Label(
            foot,
            text="HTTP → host.py",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.mono, 7),
        ).pack(side="left", padx=12)
        tk.Label(
            foot,
            text="single COM owner",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.mono, 7),
        ).pack(side="right", padx=12)

    def build_side(self, parent: tk.Frame) -> None:
        side = tk.Frame(parent, bg=BG)
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(3, weight=1)

        self.build_monitor_panel(side)
        self.build_layout_panel(side)
        self.build_stream_panel(side)
        self.build_log_panel(side)

    def build_monitor_panel(self, parent: tk.Frame) -> None:
        panel = self.panel(parent)
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        state = tk.Label(
            panel,
            textvariable=self.run_state_var,
            bg=PANEL,
            fg=MUTED,
            font=self.ui_font(self.mono, 8),
        )
        self.panel_head(panel, "MONITOR", state)

        body = tk.Frame(panel, bg=PANEL, padx=14, pady=12)
        body.pack(fill="x")
        body.grid_columnconfigure(1, weight=1)

        tk.Label(
            body,
            text="SOURCE",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.mono, 8),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.mode_frame = tk.Frame(
            body,
            bg=PANEL,
            highlightbackground=LINE,
            highlightthickness=1,
        )
        self.mode_frame.grid(
            row=0, column=1, sticky="ew", pady=(0, 8), padx=(12, 0)
        )
        self.mode_buttons: dict[str, tk.Button] = {}
        for index, (key, label) in enumerate(
            (("demo", "DEMO"), ("live", "LIVE · WINDOWS"))
        ):
            button = tk.Button(
                self.mode_frame,
                text=label,
                command=lambda value=key: self.choose_mode(value),
                bd=0,
                relief="flat",
                highlightthickness=0,
                font=self.ui_font(self.mono, 8),
                cursor="hand2",
                takefocus=False,
            )
            button.grid(row=0, column=index, sticky="nsew")
            self.mode_frame.grid_columnconfigure(index, weight=1)
            self.mode_buttons[key] = button

        tk.Label(
            body,
            text="INTERVAL",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.mono, 8),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        interval_row = tk.Frame(body, bg=PANEL)
        interval_row.grid(
            row=1, column=1, sticky="ew", pady=(0, 10), padx=(12, 0)
        )
        self.interval_entry = tk.Entry(
            interval_row,
            textvariable=self.interval_var,
            bg="#0a0806",
            fg=INK,
            insertbackground=INK,
            bd=0,
            relief="flat",
            highlightbackground=LINE,
            highlightcolor=ACCENT,
            highlightthickness=1,
            font=self.ui_font(self.mono, 11),
            width=9,
        )
        self.interval_entry.pack(side="left", ipady=6)
        self.interval_entry.bind("<Return>", self.on_interval_commit)
        self.interval_entry.bind("<FocusOut>", self.on_interval_commit)
        tk.Label(
            interval_row,
            text="S",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.mono, 8),
        ).pack(side="left", padx=(7, 0))

        actions = tk.Frame(body, bg=PANEL)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew")
        actions.grid_columnconfigure(0, weight=3)
        actions.grid_columnconfigure(1, weight=1)
        self.start_button = self.button(
            actions,
            "Start monitor",
            self.start_monitor,
            primary=True,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.stop_button = self.button(
            actions, "Stop", self.stop_monitor, primary=False
        )
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.error_label = tk.Label(
            body,
            textvariable=self.error_var,
            bg=PANEL,
            fg=ERR_TEXT,
            font=self.ui_font(self.sans, 9),
            anchor="w",
            justify="left",
            wraplength=330,
        )
        self.error_label.grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def build_layout_panel(self, parent: tk.Frame) -> None:
        panel = self.panel(parent)
        panel.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        hint = tk.Label(
            panel,
            text="串口切换",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.sans, 8),
        )
        self.panel_head(panel, "LAYOUT", hint)

        body = tk.Frame(panel, bg=PANEL, padx=14, pady=12)
        body.pack(fill="x")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self.layout_buttons: dict[str, tk.Button] = {}
        specs = (
            ("portrait", "PORTRAIT\n172 × 320"),
            ("landscape", "LANDSCAPE\n320 × 172"),
        )
        for column, (key, label) in enumerate(specs):
            button = tk.Button(
                body,
                text=label,
                command=lambda value=key: self.choose_layout(value),
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground=LINE,
                bg=PANEL_2,
                fg=MUTED,
                activebackground=PANEL_2,
                activeforeground=INK,
                font=self.ui_font(self.mono, 8),
                justify="left",
                anchor="w",
                padx=10,
                pady=8,
                cursor="hand2",
                takefocus=False,
            )
            pad = (0, 4) if column == 0 else (4, 0)
            button.grid(
                row=0, column=column, sticky="ew", padx=pad
            )
            self.layout_buttons[key] = button

        tk.Label(
            body,
            text="运行中也可切换，不停止采集。",
            bg=PANEL,
            fg=DIM,
            font=self.ui_font(self.sans, 9),
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def build_stream_panel(self, parent: tk.Frame) -> None:
        panel = self.panel(parent)
        panel.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.panel_head(panel, "STREAM")

        body = tk.Frame(panel, bg=PANEL, padx=14, pady=10)
        body.pack(fill="x")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        items = (
            ("period", "PERIOD"),
            ("last", "LAST SEND"),
            ("threads", "THREADS"),
            ("seq", "SEQ"),
        )
        for index, (key, label) in enumerate(items):
            cell = tk.Frame(body, bg=PANEL)
            row, column = divmod(index, 2)
            cell.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 10) if column == 0 else (10, 0),
                pady=(5, 5),
            )
            tk.Label(
                cell,
                text=label,
                bg=PANEL,
                fg=DIM,
                font=self.ui_font(self.mono, 7),
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                cell,
                textvariable=self.stat_vars[key],
                bg=PANEL,
                fg=INK,
                font=self.ui_font(self.mono, 11),
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

    def build_log_panel(self, parent: tk.Frame) -> None:
        panel = self.panel(parent)
        panel.grid(row=3, column=0, sticky="nsew")
        clear = tk.Button(
            panel,
            text="CLEAR",
            command=self.clear_log,
            bg=PANEL,
            fg=DIM,
            activebackground=PANEL,
            activeforeground=ACCENT,
            bd=0,
            highlightthickness=0,
            font=self.ui_font(self.mono, 7),
            cursor="hand2",
            takefocus=False,
        )
        self.panel_head(panel, "EVENT LOG", clear)

        text_frame = tk.Frame(panel, bg=PANEL)
        text_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            text_frame,
            bg=PANEL,
            fg=MUTED,
            insertbackground=INK,
            bd=0,
            highlightthickness=0,
            font=self.ui_font(self.mono, 8),
            wrap="word",
            height=7,
            padx=12,
            pady=9,
            state="disabled",
            cursor="arrow",
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("dim", foreground=DIM)
        self.log_text.tag_configure("ok", foreground=OK)
        self.log_text.tag_configure("err", foreground=ERR_TEXT)
        self.log_text.tag_configure("info", foreground=MUTED)

    def button(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        *,
        primary: bool,
    ) -> tk.Button:
        if primary:
            bg = ACCENT
            fg = "#160c07"
            active_bg = "#ff744c"
            active_fg = "#160c07"
            font = self.ui_font(self.mono, 9, True)
        else:
            bg = PANEL_2
            fg = MUTED
            active_bg = PANEL_2
            active_fg = INK
            font = self.ui_font(self.mono, 8)
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            disabledforeground=DIM,
            bd=0,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            font=font,
            pady=9,
            cursor="hand2",
            takefocus=False,
        )

    # ------------------------------------------------------------------
    # state and controls
    # ------------------------------------------------------------------

    def choose_mode(self, mode: str) -> None:
        if self.busy or mode == self.mode:
            return
        self.mode = mode
        self.mode_var.set(mode)
        self.update_mode_buttons()
        if self.running:
            self.append_log("source changed; press restart to apply", "dim")

    def on_interval_commit(self, _event: Optional[tk.Event] = None) -> None:
        value = self.read_interval()
        if value is None:
            self.interval_var.set(f"{self.interval:.1f}")
            return
        if abs(value - self.interval) > 1e-9:
            self.interval = value
            self.interval_var.set(f"{value:.1f}")
            if self.running:
                self.append_log(
                    "interval changed; press restart to apply", "dim"
                )

    def read_interval(self) -> Optional[float]:
        try:
            value = float(self.interval_var.get())
        except ValueError:
            self.set_error("interval 必须是数字")
            return None
        if not 0.2 <= value <= 60.0:
            self.set_error("interval 必须在 0.2–60 秒之间")
            return None
        return value

    def start_monitor(self) -> None:
        if self.busy:
            return
        interval = self.read_interval()
        if interval is None:
            return
        self.interval = interval
        self.set_error("")
        self.invalidate_polls()
        self.set_busy(True)
        self.append_log(
            f"start {self.mode} · {interval:.1f}s · {self.layout}", "info"
        )
        self.run_action(
            "start", self.client.start, self.mode, interval, self.layout
        )

    def stop_monitor(self) -> None:
        if self.busy:
            return
        self.invalidate_polls()
        self.set_busy(True)
        self.append_log("stop monitor", "info")
        self.run_action("stop", self.client.stop)

    def choose_layout(self, layout: str) -> None:
        if self.busy or layout == self.layout:
            return
        previous = self.layout
        self.layout = layout
        self.set_layout_ui(layout)
        self.append_log(f"layout → {layout}", "info")
        self.invalidate_polls()
        self.set_busy(True)
        self.run_action(
            "layout",
            self.client.set_layout,
            layout,
            context={"previous": previous},
        )

    def run_action(
        self,
        kind: str,
        function: Callable[..., dict[str, Any]],
        *args: Any,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        def worker() -> None:
            try:
                result = function(*args)
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                self.events.put(("action", kind, False, str(exc), context))
                return
            self.events.put(("action", kind, True, result, context))

        threading.Thread(target=worker, daemon=True).start()

    def invalidate_polls(self) -> None:
        self.poll_token += 1
        self.poll_inflight = False

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.update_controls()

    def set_layout_ui(self, layout: str) -> None:
        self.dims_var.set("320 × 172" if layout == "landscape" else "172 × 320")
        for key, button in self.layout_buttons.items():
            if key == layout:
                button.configure(
                    bg="#1d120b",
                    fg=INK,
                    activebackground="#1d120b",
                    activeforeground=INK,
                    highlightbackground=ACCENT,
                )
            else:
                button.configure(
                    bg=PANEL_2,
                    fg=MUTED,
                    activebackground=PANEL_2,
                    activeforeground=INK,
                    highlightbackground=LINE,
                )

    def update_mode_buttons(self) -> None:
        for key, button in self.mode_buttons.items():
            if key == self.mode:
                button.configure(
                    bg=INK,
                    fg=BG,
                    activebackground=INK,
                    activeforeground=BG,
                )
            else:
                button.configure(
                    bg=PANEL_2,
                    fg=MUTED,
                    activebackground="#1a1710",
                    activeforeground=INK,
                )

    def update_controls(self) -> None:
        if self.busy:
            self.start_button.configure(text="Working…")
        elif self.running:
            self.start_button.configure(text="Restart monitor")
        else:
            self.start_button.configure(text="Start monitor")

        widget_state = "disabled" if self.busy else "normal"
        self.start_button.configure(state=widget_state)
        self.stop_button.configure(
            state="normal" if self.running and not self.busy else "disabled"
        )
        self.interval_entry.configure(state=widget_state)
        for button in self.mode_buttons.values():
            button.configure(state=widget_state)
        for button in self.layout_buttons.values():
            button.configure(state=widget_state)
        self.update_mode_buttons()
        self.set_layout_ui(self.layout)

    def set_error(self, message: str) -> None:
        if message and message != self.last_error:
            self.append_log(f"error: {message}", "err")
        self.last_error = message
        self.error_var.set(message)

    def set_serial_state(self, serial: Optional[dict[str, Any]]) -> None:
        if not serial:
            self.serial_var.set("HOST · OFFLINE")
            self.serial_dot.itemconfigure(1, fill=ACCENT)
            return
        info = serial.get("serial") or {}
        links = info.get("links") or {}
        active = links.get("active") or (
            "serial" if info.get("open") else "none"
        )
        fake = bool(serial.get("fake"))
        if fake:
            port = info.get("port") or "OPEN"
            self.serial_var.set(f"FAKE · {port}")
            self.serial_dot.itemconfigure(1, fill=WARN)
        elif active == "ble":
            name = (links.get("ble") or {}).get("name") or "LVGL-C6-PERF"
            self.serial_var.set(f"BLE · {name}")
            self.serial_dot.itemconfigure(1, fill=OK)
        elif active == "serial":
            port = (links.get("serial") or {}).get("port") or "OPEN"
            self.serial_var.set(f"UART · {port}")
            self.serial_dot.itemconfigure(1, fill=OK)
        else:
            self.serial_var.set("LINK · CLOSED")
            self.serial_dot.itemconfigure(1, fill=WARN)

    # ------------------------------------------------------------------
    # polling
    # ------------------------------------------------------------------

    def poll(self) -> None:
        if self.closing:
            return
        if not self.busy and not self.poll_inflight:
            self.start_poll()
        self.poll_after = self.root.after(POLL_MS, self.poll)

    def start_poll(self) -> None:
        self.poll_inflight = True
        token = self.poll_token
        threading.Thread(
            target=self.poll_worker, args=(token,), daemon=True
        ).start()

    def poll_worker(self, token: int) -> None:
        try:
            perf = self.client.status()
            serial = self.client.serial_status()
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.events.put(("poll_error", token, str(exc)))
            return
        self.events.put(("poll", token, perf, serial))

    def drain_events(self) -> None:
        if self.closing:
            return
        while True:
            try:
                action = self.tray_events.get_nowait()
            except queue.Empty:
                break
            if action == "show":
                self.show_window()
            elif action == "exit":
                self.quit()
                return
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "poll":
                    self.handle_poll(event[1], event[2], event[3])
                elif kind == "poll_error":
                    self.handle_poll_error(event[1], str(event[2]))
                elif kind == "action":
                    self.handle_action(
                        str(event[1]), bool(event[2]), event[3], event[4]
                    )
        except queue.Empty:
            pass
        self.drain_after = self.root.after(80, self.drain_events)

    def handle_poll(
        self, token: int, perf: dict[str, Any], serial: dict[str, Any]
    ) -> None:
        if token != self.poll_token:
            return
        self.poll_inflight = False
        self.set_serial_state(serial)
        if self.busy:
            return
        if not self.host_seen:
            self.host_seen = True
            self.append_log("host connected", "ok")
        previous_poll_error = self.last_poll_error
        self.last_poll_error = ""
        if previous_poll_error and self.last_error == previous_poll_error:
            self.set_error("")
        self.last_perf = perf
        self.ingest_sample(perf)
        if not self.initialized:
            self.initialized = True
            self.mode = str(perf.get("mode") or self.mode)
            try:
                self.interval = float(perf.get("interval_s", self.interval))
            except (TypeError, ValueError):
                self.interval = 0.3
            self.interval_var.set(f"{self.interval:.1f}")
        layout = str(perf.get("layout") or self.layout)
        if layout in ("portrait", "landscape"):
            self.layout = layout
        self.running = bool(perf.get("running"))
        self.update_controls()
        self.update_status(perf)
        self.draw_preview()

    def handle_poll_error(self, token: int, message: str) -> None:
        if token != self.poll_token:
            return
        self.poll_inflight = False
        self.set_serial_state(None)
        self.run_state_var.set("OFFLINE")
        self.host_seen = False
        if message != self.last_poll_error:
            self.last_poll_error = message
            self.set_error(message)
        self.draw_preview()

    def update_status(self, perf: dict[str, Any]) -> None:
        state = str(perf.get("state") or "idle")
        running = bool(perf.get("running"))
        sample = perf.get("sample")
        if state == "error":
            self.run_state_var.set("ERROR")
        elif running:
            self.run_state_var.set("RUNNING")
        else:
            self.run_state_var.set("IDLE")
        period_ms = perf.get("period_ms")
        self.stat_vars["period"].set(
            f"{int(period_ms)} MS" if period_ms else "--"
        )
        self.stat_vars["last"].set(str(perf.get("last_sent_at") or "--"))
        self.stat_vars["threads"].set(
            f"{sample.get('thread_count')}T" if sample else "--"
        )
        self.stat_vars["seq"].set(
            str(sample.get("seq")) if sample else "--"
        )
        error = perf.get("last_error")
        if error:
            self.set_error(str(error))

    def ingest_sample(self, perf: dict[str, Any]) -> None:
        sample = perf.get("sample")
        if not isinstance(sample, dict):
            return
        seq = sample.get("seq")
        if not isinstance(seq, int) or seq == self.last_seq:
            return
        if self.last_seq is not None and seq < self.last_seq:
            self.cpu_history.clear()
            self.down_history.clear()
            self.up_history.clear()
        self.last_seq = seq
        cpu = sample.get("cpu")
        if isinstance(cpu, (int, float)):
            self.cpu_history.append(max(0, min(100, int(cpu))))
        else:
            self.cpu_history.append(0)
        down = sample.get("down_kib_s") or 0
        up = sample.get("up_kib_s") or 0
        self.down_history.append(
            max(0, min(100, int(down * 100 / (40 * 1024))))
        )
        self.up_history.append(
            max(0, min(100, int(up * 100 / (8 * 1024))))
        )
        for history in (
            self.cpu_history,
            self.down_history,
            self.up_history,
        ):
            del history[:-60]

    def handle_action(
        self,
        kind: str,
        ok: bool,
        data: Any,
        context: Optional[dict[str, Any]],
    ) -> None:
        self.set_busy(False)
        if ok:
            self.set_error("")
        if kind == "start":
            if ok:
                result = data if isinstance(data, dict) else {}
                self.mode = str(result.get("mode") or self.mode)
                self.layout = str(result.get("layout") or self.layout)
                try:
                    self.interval = float(
                        result.get("interval_s", self.interval)
                    )
                except (TypeError, ValueError):
                    pass
                self.interval_var.set(f"{self.interval:.1f}")
                self.last_seq = None
                self.cpu_history.clear()
                self.down_history.clear()
                self.up_history.clear()
                self.append_log(
                    f"armed · {self.mode} · {self.layout}", "ok"
                )
            else:
                self.set_error(str(data))
        elif kind == "stop":
            if ok:
                self.append_log("monitor stopped", "ok")
            else:
                self.set_error(str(data))
        elif kind == "layout":
            previous = (context or {}).get("previous")
            if ok:
                self.append_log(f"layout → {self.layout}", "ok")
            else:
                if previous in ("portrait", "landscape"):
                    self.layout = str(previous)
                self.set_error(str(data))
        self.initialized = True
        self.update_controls()
        self.poll_now()

    def poll_now(self) -> None:
        if self.closing or self.poll_inflight:
            return
        self.start_poll()

    # ------------------------------------------------------------------
    # log
    # ------------------------------------------------------------------

    def append_log(self, message: str, kind: str = "info") -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", stamp, "dim")
        self.log_text.insert("end", f"  {message}\n", kind)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 160:
            self.log_text.delete("1.0", f"{line_count - 160}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------

    def on_canvas_resize(self, _event: tk.Event) -> None:
        if self.resize_after is not None:
            self.root.after_cancel(self.resize_after)
        self.resize_after = self.root.after(60, self.draw_preview)

    def draw_preview(self) -> None:
        self.resize_after = None
        if self.closing:
            return
        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 200)
        self.canvas.delete("all")

        for x in range(0, width, 38):
            self.canvas.create_line(x, 0, x, height, fill="#100e0a")
        for y in range(0, height, 38):
            self.canvas.create_line(0, y, width, y, fill="#100e0a")

        if self.layout == "landscape":
            screen_w, screen_h = 320, 172
        else:
            screen_w, screen_h = 172, 320
        scale = min(
            (width - 130) / screen_w,
            (height - 110) / screen_h,
        )
        scale = max(0.55, min(scale, 2.0))
        ox = (width - screen_w * scale) / 2
        oy = (height - screen_h * scale) / 2

        self.canvas.create_rectangle(
            ox + 10,
            oy + 14,
            ox + screen_w * scale + 10,
            oy + screen_h * scale + 14,
            fill="#040302",
            outline="",
        )
        self.canvas.create_rectangle(
            ox - 14,
            oy - 14,
            ox + screen_w * scale + 14,
            oy + screen_h * scale + 14,
            fill="#0b0906",
            outline="#241d14",
        )
        self.canvas.create_rectangle(
            ox - 6,
            oy - 6,
            ox + screen_w * scale + 6,
            oy + screen_h * scale + 6,
            fill="#050403",
            outline="#3a2f22",
        )
        self.canvas.create_line(
            ox - 6,
            oy + 16,
            ox - 6,
            oy - 6,
            ox + 16,
            oy - 6,
            fill="#6b3a22",
        )

        painter = ScreenPainter(
            self.canvas, ox, oy, scale, self.font, self.mono
        )
        perf = self.last_perf or {}
        sample = perf.get("sample")
        if not isinstance(sample, dict):
            sample = {}
        if self.layout == "landscape":
            self.draw_landscape(painter, perf, sample)
        else:
            self.draw_portrait(painter, perf, sample)

    def draw_portrait(
        self,
        p: ScreenPainter,
        perf: dict[str, Any],
        sample: dict[str, Any],
    ) -> None:
        p.rect(0, 0, 172, 320, BG)
        p.rect(0, 0, 172, 26, STATUS_BG)
        p.rect(8, 11, 4, 4, ACCENT)
        p.text(15, 8, "PERF", 8, INK, self.mono)
        host = short_text(sample.get("host"), 11) or "DESKTOP"
        p.text(82, 9, host, 8, DIM, self.mono, anchor="n")
        p.text(164, 7, clock_text(sample), 10, INK, self.mono, anchor="ne")
        p.line(0, 26, 172, 26, LINE)

        cpu = number_or_none(sample.get("cpu"))
        cpu_color = INK
        if cpu is not None and cpu >= 90:
            cpu_color = ACCENT
        elif cpu is not None and cpu >= 75:
            cpu_color = WARN
        threads = thread_count(sample)
        p.text(8, 30, "CPU LOAD", 8, MUTED, self.mono)
        trend = self.cpu_trend()
        p.text(132, 30, trend, 8, ACCENT if trend != "±0" else DIM,
               self.mono, anchor="ne")
        p.text(164, 30, f" · {threads}T", 8, DIM, self.mono, anchor="ne")
        cpu_text = "--" if cpu is None else f"{int(cpu):02d}"
        p.text(8, 33, cpu_text, 60, cpu_color, self.cond, bold=True)
        if cpu is not None:
            unit_x = min(8 + p.measure(cpu_text, 60, self.cond, True) + 1,
                         118)
            p.text(unit_x, 49, "%", 8, MUTED, self.mono)
        freq = number_or_none(sample.get("freq_mhz"))
        p.text(153, 49, f"{freq / 1000:.2f}" if freq else "--", 14, INK,
               self.cond, anchor="ne")
        p.text(154, 53, "GHz", 8, MUTED, self.mono)
        temp = number_or_none(sample.get("temp_c"))
        temp_text = "--" if temp is None else str(int(temp))
        p.text(153, 67, temp_text, 14, INK, self.cond, anchor="ne")
        p.text(154, 71, "°C", 8, MUTED, self.mono)
        p.line(123.5, 48, 123.5, 93, LINE_SOFT)

        p.line(0, 104, 172, 104, LINE)
        self.draw_tape(p, 0, 105, 172, 33, 8, 136)
        p.line(0, 146, 172, 146, LINE)
        p.line(0, 200, 172, 200, LINE)
        p.line(86, 153, 86, 194, LINE_SOFT)

        mem_pct = memory_percent(sample)
        p.text(8, 152, "MEM", 8, MUTED, self.mono)
        p.text(78, 152, memory_sub(sample), 8, DIM, self.mono, anchor="ne")
        p.text(8, 157, percent_text(mem_pct), 26, INK, self.cond, bold=True)
        if mem_pct is not None:
            p.text(46, 162, "%", 8, MUTED, self.mono)
        p.rect(8, 190, 70, 3, LINE_SOFT)
        if mem_pct:
            p.rect(8, 190, 70 * mem_pct / 100, 3, INK)

        gpu = number_or_none(sample.get("gpu"))
        p.text(94, 152, "GPU", 8, MUTED, self.mono)
        p.text(164, 152, gpu_temp_text(sample), 8, DIM, self.mono,
               anchor="ne")
        p.text(94, 157, percent_text(gpu), 26, INK, self.cond, bold=True)
        if gpu is not None:
            p.text(132, 162, "%", 8, MUTED, self.mono)
        p.rect(94, 190, 70, 3, LINE_SOFT)
        if gpu:
            p.rect(94, 190, 70 * gpu / 100, 3, INK)

        p.text(8, 205, "NET", 8, MUTED, self.mono)
        p.text(164, 205, ping_text(sample), 8, DIM, self.mono, anchor="ne")
        down = mib_text(sample.get("down_kib_s"))
        up = mib_text(sample.get("up_kib_s"))
        p.text(8, 217, "↓", 8, MUTED, self.mono)
        p.text(16, 211, down, 22, INK, self.cond, bold=True)
        p.text(63, 216, "MB/S", 8, DIM, self.mono)
        p.text(111, 217, "↑", 8, ACCENT, self.mono)
        p.text(119, 211, up, 22, INK, self.cond, bold=True)
        p.text(149, 216, "MB/S", 8, DIM, self.mono)
        self.draw_net_chart(p, 0, 238, 172, 18)

        p.line(0, 256, 172, 256, LINE)
        p.text(8, 260, "THREADS", 8, MUTED, self.mono)
        p.text(164, 260, f"PEAK {thread_peak(sample)}%", 8, DIM,
               self.mono, anchor="ne")
        self.draw_threads(p, sample, 8, 275, 156, 4, 18, 18)

        p.line(0, 296, 172, 296, LINE)
        state = self.footer_state(perf, sample)
        p.rect(8, 305, 4, 4, ACCENT)
        p.text(15, 303, state, 8, MUTED, self.mono)
        p.text(52, 303, self.footer_period(perf, sample), 8, DIM,
               self.mono, anchor="n")
        p.text(164, 303, "C6/01", 8, DIM, self.mono, anchor="ne")

    def draw_landscape(
        self,
        p: ScreenPainter,
        perf: dict[str, Any],
        sample: dict[str, Any],
    ) -> None:
        p.rect(0, 0, 320, 172, BG)
        p.rect(0, 0, 320, 20, STATUS_BG)
        p.rect(8, 8, 4, 4, ACCENT)
        p.text(15, 6, "PERF", 8, INK, self.mono)
        host = short_text(sample.get("host"), 14) or "DESKTOP"
        p.text(112, 6, host, 8, DIM, self.mono, anchor="n")
        p.text(312, 5, clock_text(sample), 10, INK, self.mono, anchor="ne")
        p.line(0, 20, 320, 20, LINE)

        cpu = number_or_none(sample.get("cpu"))
        cpu_color = INK
        if cpu is not None and cpu >= 90:
            cpu_color = ACCENT
        elif cpu is not None and cpu >= 75:
            cpu_color = WARN
        threads = thread_count(sample)
        p.text(8, 24, "CPU LOAD", 8, MUTED, self.mono)
        trend = self.cpu_trend()
        p.text(102, 24, trend, 8, ACCENT if trend != "±0" else DIM,
               self.mono, anchor="ne")
        p.text(134, 24, f" · {threads}T", 8, DIM, self.mono, anchor="ne")
        cpu_text = "--" if cpu is None else f"{int(cpu):02d}"
        cpu_size = 46 if cpu is not None and cpu >= 100 else 52
        p.text(8, 32, cpu_text, cpu_size, cpu_color,
               self.cond, bold=True)
        if cpu is not None:
            unit_x = min(
                8 + p.measure(cpu_text, cpu_size, self.cond, True) + 1, 82
            )
            p.text(unit_x, 39, "%", 8, MUTED, self.mono)
        p.line(84, 37, 84, 82, LINE_SOFT)
        freq = number_or_none(sample.get("freq_mhz"))
        p.text(115, 36, f"{freq / 1000:.2f}" if freq else "--", 14, INK,
               self.cond, anchor="ne")
        p.text(116, 40, "GHz", 8, MUTED, self.mono)
        temp = number_or_none(sample.get("temp_c"))
        temp_text = "--" if temp is None else str(int(temp))
        p.text(115, 55, temp_text, 14, INK, self.cond, anchor="ne")
        p.text(116, 59, "°C", 8, MUTED, self.mono)

        p.line(0, 90, 320, 90, LINE)
        self.draw_tape(p, 0, 91, 320, 30, 8, 121, tag="CPU · 18S")

        p.line(136, 28, 136, 82, LINE_SOFT)
        p.line(192, 28, 192, 82, LINE_SOFT)
        self.draw_metric_landscape(p, 142, sample, memory=True)
        self.draw_metric_landscape(p, 198, sample, memory=False)
        self.draw_net_landscape(p, sample)

        p.line(0, 130, 320, 130, LINE)
        p.text(8, 134, "THREADS", 8, MUTED, self.mono)
        p.text(312, 134, f"PEAK {thread_peak(sample)}%", 8, DIM,
               self.mono, anchor="ne")
        self.draw_threads(p, sample, 8, 143, 304, 4, 12, 34)

        p.line(0, 156, 320, 156, LINE)
        state = self.footer_state(perf, sample)
        p.rect(8, 164, 3, 3, ACCENT)
        p.text(14, 161, state, 8, MUTED, self.mono)
        p.text(160, 161, self.footer_period(perf, sample), 8, DIM,
               self.mono, anchor="n")
        p.text(312, 161, "C6/01", 8, DIM, self.mono, anchor="ne")

    def draw_metric_landscape(
        self,
        p: ScreenPainter,
        x: int,
        sample: dict[str, Any],
        *,
        memory: bool,
    ) -> None:
        if memory:
            value = memory_percent(sample)
            label = "MEM"
            sub = memory_sub(sample)
        else:
            value = number_or_none(sample.get("gpu"))
            label = "GPU"
            sub = gpu_temp_text(sample)
        p.text(x, 24, label, 8, MUTED, self.mono)
        p.text(x, 34, percent_text(value), 26, INK, self.cond, bold=True)
        if value is not None:
            p.text(x, 41, "%", 8, MUTED, self.mono)
        p.text(x, 64, sub, 8, DIM, self.mono)
        p.rect(x, 82, 44, 3, LINE_SOFT)
        if value:
            p.rect(x, 82, 44 * value / 100, 3, INK)

    def draw_net_landscape(
        self, p: ScreenPainter, sample: dict[str, Any]
    ) -> None:
        p.text(252, 24, "NET", 8, MUTED, self.mono)
        p.text(314, 24, ping_text(sample, short=True), 8, DIM, self.mono,
               anchor="ne")
        p.text(254, 40, "↓", 8, MUTED, self.mono)
        p.text(292, 34, mib_text(sample.get("down_kib_s")), 14, INK,
               self.cond, bold=True, anchor="ne")
        p.text(294, 39, "MB/S", 8, DIM, self.mono)
        p.text(254, 57, "↑", 8, ACCENT, self.mono)
        p.text(292, 51, mib_text(sample.get("up_kib_s")), 14, INK,
               self.cond, bold=True, anchor="ne")
        p.text(294, 56, "MB/S", 8, DIM, self.mono)
        p.line(248, 28, 248, 72, LINE_SOFT)
        self.draw_net_chart(p, 248, 72, 72, 18)

    def draw_tape(
        self,
        p: ScreenPainter,
        x: int,
        y: int,
        width: int,
        height: int,
        label_y: int,
        bottom_label_y: int,
        tag: Optional[str] = None,
    ) -> None:
        p.rect(x, y, width, height, TAPE)
        top = y + 2
        bottom = y + height - 4
        for index in range(10, 60, 10):
            grid_x = x + index * width / 60
            p.line(grid_x, top, grid_x, bottom, LINE, 1)
        threshold = top + (100 - 80) * (bottom - top) / 100
        p.line(x, threshold, x + width - 1, threshold, "#4a4131", 1,
               dash=(2, 3))

        values = self.history_window(self.cpu_history)
        points = [(x, bottom)]
        line_points: list[tuple[float, float]] = []
        for index, value in enumerate(values):
            px = x + index * (width - 1) / 59
            py = bottom - value * (bottom - top) / 100
            line_points.append((px, py))
        points.extend(line_points)
        points.append((x + width - 1, bottom))
        p.polygon(points, "#211c13")
        for first, second in zip(line_points, line_points[1:]):
            p.line(first[0], first[1], second[0], second[1], MUTED, 1)
        head_x, head_y = line_points[-1]
        p.rect(head_x - 2, head_y - 2, 4, 4, ACCENT)

        if tag:
            p.rect(4, y + 1, int(p.measure(tag, 8) + 4), 9, TAPE)
            p.text(6, y + 1, tag, 8, DIM, self.mono)
        p.rect(x + width - 25, y + 1, 18, 9, TAPE)
        p.text(
            x + width - 6,
            y + 1,
            "80",
            8,
            DIM,
            self.mono,
            anchor="ne",
        )
        p.text(x + 6, bottom_label_y, "-18S", 8, DIM, self.mono)
        p.text(x + width - 6, bottom_label_y, "NOW", 8, DIM, self.mono,
               anchor="ne")

    def draw_net_chart(
        self, p: ScreenPainter, x: int, y: int, width: int, height: int
    ) -> None:
        p.rect(x, y, width, height, TAPE)
        mid = y + height / 2
        p.line(x, mid, x + width - 1, mid, LINE_SOFT, 1)
        down = self.history_window(self.down_history)
        up = self.history_window(self.up_history)
        amp = height / 2 - 1
        down_points = [
            (x + index * (width - 1) / 59,
             mid - value * amp / 100)
            for index, value in enumerate(down)
        ]
        up_points = [
            (x + index * (width - 1) / 59,
             mid + value * amp / 100)
            for index, value in enumerate(up)
        ]
        for points, color in ((down_points, INK), (up_points, ACCENT)):
            for first, second in zip(points, points[1:]):
                p.line(first[0], first[1], second[0], second[1], color, 1)
        p.rect(down_points[-1][0] - 1, down_points[-1][1] - 1, 2, 2, INK)

    def draw_threads(
        self,
        p: ScreenPainter,
        sample: dict[str, Any],
        x: int,
        y: int,
        span: int,
        gap: int,
        bar_height: int,
        max_width: int,
    ) -> None:
        count = thread_count(sample)
        bars = sample.get("bars") if isinstance(sample, dict) else None
        if not isinstance(bars, list):
            bars = []
        bar_width = (span - (count - 1) * gap) // count
        bar_width = max(6, min(max_width, bar_width))
        group_width = count * bar_width + (count - 1) * gap
        start_x = x + (span - group_width) // 2
        peak = thread_peak(sample)
        for index in range(count):
            value = bars[index] if index < len(bars) else 0
            value = max(0, min(100, int(value or 0)))
            bx = start_x + index * (bar_width + gap)
            p.rect(bx, y, bar_width, bar_height, LINE_SOFT)
            fill_height = max(1, int(bar_height * value / 100))
            hot = value == peak and peak > 0
            p.rect(
                bx,
                y + bar_height - fill_height,
                bar_width,
                fill_height,
                ACCENT if hot else INK,
            )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def cpu_trend(self) -> str:
        if len(self.cpu_history) < 6:
            return "±0"
        delta = self.cpu_history[-1] - self.cpu_history[-6]
        if delta > 0:
            return f"+{delta}"
        if delta < 0:
            return f"−{abs(delta)}"
        return "±0"

    @staticmethod
    def history_window(values: list[int]) -> list[int]:
        values = values[-60:]
        if not values:
            return [0] * 60
        if len(values) < 60:
            values = [values[0]] * (60 - len(values)) + values
        return values

    def footer_state(
        self, perf: dict[str, Any], sample: dict[str, Any]
    ) -> str:
        if perf.get("state") == "error":
            return "ERR"
        if perf.get("running"):
            return "LIVE"
        if sample:
            return "HOLD"
        return "SIM" if self.mode == "demo" else "IDLE"

    def footer_period(
        self, perf: dict[str, Any], sample: dict[str, Any]
    ) -> str:
        if perf.get("running"):
            try:
                return f"{float(perf.get('interval_s')):.1f}S"
            except (TypeError, ValueError):
                return "--"
        return "HOLD" if sample else "--"

    def open_web(self) -> None:
        webbrowser.open(self.client.base_url + "/perf/")

    def start_tray(self) -> None:
        if self.closing or self.tray is not None:
            return
        icon = (
            HOST_DIR.parents[2]
            / "scripts"
            / "launchers"
            / "icons"
            / "lvgl-verify-loop-viewer.ico"
        )
        tray = TrayIcon(
            "PERF TAPE · Python GUI",
            icon_path=icon,
            on_show=lambda: self.tray_events.put("show"),
            on_exit=lambda: self.tray_events.put("exit"),
        )
        if tray.start():
            self.tray = tray
            self.append_log(
                "tray icon ready; closing hides the window", "dim"
            )
        else:
            self.append_log("tray icon unavailable; close exits", "dim")

    def on_close(self) -> None:
        if self.closing:
            return
        if self.tray is None:
            self.quit()
            return
        self.root.withdraw()
        self.append_log(
            "window hidden to tray; double-click the tray icon to restore",
            "dim",
        )

    def show_window(self) -> None:
        if self.closing:
            return
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()
        self.poll_now()

    def quit(self, *, close_link: bool = True) -> None:
        if self.closing:
            return
        self.closing = True
        if close_link:
            try:
                self.client.close_link()
                self.append_log("link closed (BLE/UART released)", "dim")
            except Exception as exc:  # noqa: BLE001 - best effort on exit
                self.append_log(f"link close failed: {exc}", "err")
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
        for after_id in (self.poll_after, self.drain_after, self.resize_after):
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        self.root.destroy()


def short_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def clock_text(sample: dict[str, Any]) -> str:
    value = sample.get("hhmm")
    if not isinstance(value, int):
        return "--:--"
    return f"{value // 100:02d}:{value % 100:02d}"


def number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def thread_count(sample: dict[str, Any]) -> int:
    value = number_or_none(sample.get("thread_count"))
    if value is None:
        return 8
    return max(1, min(16, int(value)))


def thread_peak(sample: dict[str, Any]) -> int:
    bars = sample.get("bars")
    if not isinstance(bars, list):
        return 0
    count = thread_count(sample)
    return max((int(value or 0) for value in bars[:count]), default=0)


def memory_percent(sample: dict[str, Any]) -> Optional[int]:
    used = number_or_none(sample.get("mem_mb"))
    total = number_or_none(sample.get("mem_total_mb"))
    if not used or not total:
        return None
    return max(0, min(100, int(round(used * 100 / total))))


def memory_sub(sample: dict[str, Any]) -> str:
    used = number_or_none(sample.get("mem_mb"))
    total = number_or_none(sample.get("mem_total_mb"))
    if not used or not total:
        return "--"
    return f"{used / 1024:.1f}/{total / 1024:.0f}G"


def gpu_temp_text(sample: dict[str, Any]) -> str:
    temp = number_or_none(sample.get("gpu_temp_c"))
    return f"{int(temp)}°C" if temp is not None else "--"


def percent_text(value: Optional[float]) -> str:
    return "--" if value is None else f"{int(value):02d}"


def mib_text(value: Any) -> str:
    number = number_or_none(value)
    return "--" if number is None else f"{number / 1024:.1f}"


def ping_text(sample: dict[str, Any], short: bool = False) -> str:
    ping = number_or_none(sample.get("ping_ms"))
    if ping is None:
        return "PING --"
    if short or ping >= 1000:
        return f"PING {int(ping)}"
    return f"PING {int(ping)} MS"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PERF TAPE tkinter control panel for the ESP32 host."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"host base URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--smoke-ms",
        type=int,
        default=0,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="close the window instead of hiding to the tray",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    root = tk.Tk()
    app = PerfGui(
        root, HostClient(args.url), tray_enabled=not args.no_tray
    )
    if args.smoke_ms > 0:
        root.after(args.smoke_ms, lambda: app.quit(close_link=False))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
