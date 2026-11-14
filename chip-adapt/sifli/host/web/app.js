(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const TERM_FONT =
    '"Cascadia Mono", "JetBrains Mono", "SFMono-Regular", Consolas, monospace';
  const TERM_SIZE = 14;
  const TERM_LINE_HEIGHT = 1.2;
  const TERMINAL_STATUSES = new Set(["ok", "failed", "cancelled"]);

  const state = {
    connected: false,
    connecting: false,
    reconnecting: false,
    autoReconnect: true,
    port: "",
    baud: 1000000,
    firstSeq: 0,
    nextSeq: 0,
    totalTx: 0,
    cursor: 0,
    lastError: "",
    stream: null,
    decoder: new TextDecoder("utf-8", { fatal: false }),
    eventsStream: null,
    activitySince: 0,
    unreadActivity: 0,
    jobId: "",
    jobKind: "",
    jobActor: "",
    jobRunning: false,
    jobPercent: 0,
    jobFinished: true,
    jobStream: null,
    jobAttaching: false,
    lastTermPercent: -1,
    currentTab: "terminal",
    toastTimer: 0,
    globalHideTimer: 0,
  };

  const term = new Terminal({
    cursorBlink: true,
    cursorStyle: "bar",
    fontFamily: TERM_FONT,
    fontSize: TERM_SIZE,
    lineHeight: TERM_LINE_HEIGHT,
    scrollback: 10000,
    convertEol: false,
    allowTransparency: true,
    theme: {
      background: "#070c11",
      foreground: "#d9e5f2",
      cursor: "#5ad6c8",
      cursorAccent: "#070c11",
      selectionBackground: "rgba(90, 214, 200, 0.25)",
      black: "#0b1118",
      red: "#ef6b73",
      green: "#69d49b",
      yellow: "#f0b85a",
      blue: "#6aa8ff",
      magenta: "#c792ea",
      cyan: "#5ad6c8",
      white: "#d9e5f2",
      brightBlack: "#53677c",
      brightRed: "#ff8b91",
      brightGreen: "#8be7b3",
      brightYellow: "#ffd27a",
      brightBlue: "#93c0ff",
      brightMagenta: "#e0b0ff",
      brightCyan: "#7bf0e2",
      brightWhite: "#ffffff",
    },
  });

  term.open($("terminal"));
  term.writeln("\x1b[2m[host] SiFli Host 就绪，连接串口后开始。\x1b[0m");

  // RT-Thread finsh already echoes every character. Local echo on top of it
  // shows each keystroke twice, so keep it off unless the user opted in.
  try {
    $("localEcho").checked =
      localStorage.getItem("sifli.localEcho") === "1";
  } catch {
    $("localEcho").checked = false;
  }

  // -- helpers -------------------------------------------------------

  function parseJson(text) {
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  }

  async function api(path, options = {}) {
    const init = { ...options };
    init.headers = {
      ...(options.headers || {}),
      "X-Sifli-Actor": "web",
    };
    if (init.body && typeof init.body !== "string") {
      init.body = JSON.stringify(init.body);
      init.headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, init);
    const payload = await response.json().catch(() => null);
    if (!response.ok || (payload && payload.ok === false)) {
      const message =
        (payload && payload.error) || `${response.status} ${response.statusText}`;
      throw new Error(message);
    }
    return payload || {};
  }

  function b64ToBytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  function toast(message, type = "info") {
    const node = $("toast");
    node.textContent = message;
    node.classList.toggle("error", type === "error");
    node.classList.add("visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      node.classList.remove("visible");
    }, 3400);
  }

  let fitCanvas = null;

  // xterm's real cell is taller than `fontSize * lineHeight` (it adds the
  // font's line box), so measuring with a canvas underestimates the row
  // height and makes the screen overflow the pane. Prefer the renderer's
  // measured dimensions when they are available, and fall back to a canvas
  // measurement for the first frame before the renderer has measured.
  function measureCell() {
    const core = term._core;
    const measured =
      core &&
      core._renderService &&
      core._renderService.dimensions &&
      core._renderService.dimensions.css &&
      core._renderService.dimensions.css.cell;
    if (measured && measured.width > 0 && measured.height > 0) {
      return { width: measured.width, height: measured.height };
    }
    fitCanvas = fitCanvas || document.createElement("canvas");
    const context = fitCanvas.getContext("2d");
    context.font = `${TERM_SIZE}px ${TERM_FONT}`;
    return {
      width: Math.max(6, context.measureText("M").width),
      height: Math.max(12, Math.round(TERM_SIZE * TERM_LINE_HEIGHT)),
    };
  }

  function fitTerminal() {
    if (state.currentTab !== "terminal") return;
    const host = $("terminal");
    const rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const cell = measureCell();
    // The canvas sits inside the host's CSS padding; subtract the real
    // padding instead of a guessed constant, and keep a few pixels at the
    // bottom so the input line never touches the pane edge.
    const style = window.getComputedStyle(host);
    const padX =
      parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const padY =
      parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const cols = Math.max(20, Math.floor((rect.width - padX) / cell.width));
    const rows = Math.max(
      6,
      Math.floor((rect.height - padY - 8) / cell.height),
    );
    try {
      term.resize(cols, rows);
    } catch {
      /* xterm can reject a resize during teardown */
    }
  }

  function setBadge(id, value) {
    const node = $(id);
    if (value === null || value === undefined || value === 0 || value === "") {
      node.classList.add("hidden");
      node.textContent = "";
      return;
    }
    node.textContent = String(value);
    node.classList.remove("hidden");
  }

  function switchTab(name) {
    if (!["terminal", "activity"].includes(name)) return;
    state.currentTab = name;
    if (location.hash !== `#${name}`) {
      history.replaceState(null, "", `#${name}`);
    }
    document.querySelectorAll(".tab[data-tab]").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.tab === name);
    });
    document.querySelectorAll(".pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === `pane-${name}`);
    });
    if (name === "activity") {
      state.unreadActivity = 0;
      setBadge("activityBadge", 0);
      const list = $("activityList");
      list.scrollTop = list.scrollHeight;
    }
    if (name === "terminal") {
      window.requestAnimationFrame(fitTerminal);
    }
  }

  function formatTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value || "");
    return date.toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function actorClass(actor) {
    if (actor === "ai") return "actor-ai";
    if (actor === "cli") return "actor-cli";
    if (actor === "web") return "actor-web";
    if (actor === "system") return "actor-system";
    return "actor-external";
  }

  function actorLabel(actor) {
    if (actor === "ai") return "AI";
    if (actor === "cli") return "CLI";
    if (actor === "web") return "WEB";
    if (actor === "system") return "SYS";
    return String(actor || "?").toUpperCase();
  }

  function activityDetail(event) {
    const data = event.data || {};
    const parts = [];
    if (data.job_id) parts.push(`#${data.job_id}`);
    if (data.percent !== null && data.percent !== undefined) {
      parts.push(`${data.percent}%`);
    }
    if (data.bytes) parts.push(`${data.bytes} B`);
    if (data.port) parts.push(data.port);
    if (data.chip) parts.push(data.chip);
    if (data.memory) parts.push(String(data.memory).toUpperCase());
    return parts.join(" · ");
  }

  function addActivity(event, unread = true) {
    const list = $("activityList");
    const item = document.createElement("li");
    item.className = "activity-item";
    if (String(event.kind || "").startsWith("job.")) {
      item.classList.add("highlight");
    }

    const time = document.createElement("span");
    time.className = "time";
    time.textContent = formatTime(event.ts);

    const actor = document.createElement("span");
    actor.className = `actor ${actorClass(event.actor)}`;
    actor.textContent = actorLabel(event.actor);

    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = event.kind || "";

    const message = document.createElement("span");
    message.className = "message";
    message.title = event.message || "";
    message.textContent = event.message || "";
    const detailText = activityDetail(event);
    if (detailText) {
      const detail = document.createElement("span");
      detail.className = "detail";
      detail.textContent = detailText;
      message.appendChild(detail);
    }

    item.append(time, actor, kind, message);
    list.appendChild(item);
    while (list.children.length > 500) {
      list.removeChild(list.firstChild);
    }
    if (state.currentTab === "activity") {
      list.scrollTop = list.scrollHeight;
    } else if (unread) {
      state.unreadActivity += 1;
      setBadge(
        "activityBadge",
        state.unreadActivity > 99 ? "99+" : state.unreadActivity,
      );
    }
  }

  async function loadActivityHistory() {
    const data = await api("/api/events?since=0");
    for (const event of data.events || []) addActivity(event, false);
    state.activitySince = Number(data.next) || 0;
    startEventsStream();
  }

  // -- SSE -----------------------------------------------------------

  function openSse(url, { onMessage, onError }) {
    const stream = new EventSource(url);
    stream.onmessage = (message) => {
      const payload = parseJson(message.data);
      if (payload) onMessage(payload, stream);
    };
    if (onError) stream.onerror = () => onError(stream);
    return stream;
  }

  function startEventsStream() {
    if (state.eventsStream) state.eventsStream.close();
    const stream = openSse(
      `/api/events/stream?since=${encodeURIComponent(state.activitySince)}`,
      {
        onMessage: (payload) => {
          for (const event of payload.events || []) {
            addActivity(event);
            handleJobEvent(event);
          }
          state.activitySince = Number(payload.next) || state.activitySince;
        },
        onError: () => {
          stream.close();
          if (state.eventsStream === stream) state.eventsStream = null;
          window.setTimeout(() => {
            if (!state.eventsStream) startEventsStream();
          }, 1200);
        },
      },
    );
    state.eventsStream = stream;
  }

  function stopSerialStream() {
    if (state.stream) {
      state.stream.close();
      state.stream = null;
    }
  }

  function startSerialStream(since) {
    stopSerialStream();
    state.cursor = Math.max(0, Number(since) || 0);
    state.decoder = new TextDecoder("utf-8", { fatal: false });
    const stream = openSse(
      `/api/stream?since=${encodeURIComponent(state.cursor)}`,
      {
        onMessage: (payload) => {
          if (payload.data_b64) {
            const text = state.decoder.decode(b64ToBytes(payload.data_b64), {
              stream: true,
            });
            if (text) term.write(text);
          }
          state.cursor = Number(payload.next) || state.cursor;
          state.firstSeq = Number(payload.first_seq) || state.firstSeq;
          state.nextSeq = Number(payload.next_seq) || state.nextSeq;
          updateStatusbar();
        },
        onError: () => {
          stream.close();
          if (state.stream === stream) state.stream = null;
          window.setTimeout(() => {
            if (!state.stream && (state.connected || state.reconnecting)) {
              startSerialStream(state.cursor);
            }
          }, 1000);
        },
      },
    );
    state.stream = stream;
  }

  // -- job visualization ---------------------------------------------

  function setJobProgress(percent, label) {
    const value =
      percent === null || percent === undefined
        ? 0
        : Math.max(0, Math.min(100, Number(percent)));
    state.jobPercent = value;
    $("jobBar").style.width = `${value}%`;
    $("jobPercent").textContent = `${value}%`;
    if (label) {
      $("globalLabel").textContent = label;
    }
    if (state.jobRunning) {
      $("globalProgress").classList.remove("hidden");
      $("globalBar").style.width = `${value}%`;
      window.clearTimeout(state.globalHideTimer);
    }
  }

  function hideGlobalProgressSoon() {
    window.clearTimeout(state.globalHideTimer);
    state.globalHideTimer = window.setTimeout(() => {
      $("globalProgress").classList.add("hidden");
      $("globalBar").style.width = "0%";
    }, 4500);
  }

  function terminalWriteJob(text, color = "36") {
    term.write(`\r\n\x1b[${color}m[${state.jobKind}] ${text}\x1b[0m\r\n`);
  }

  function appendJobEvent(event) {
    const text = String(event.text || "");
    if (!text) return;
    if (event.stream === "status") {
      terminalWriteJob(text);
      return;
    }
    const match = text.match(/^\s*(\d+)\s*%\s*$/);
    if (match) {
      const value = Math.min(100, Math.max(0, parseInt(match[1], 10)));
      if (value !== state.lastTermPercent) {
        state.lastTermPercent = value;
        terminalWriteJob(`${value}%`);
      }
      return;
    }
    if (event.stream === "stderr") {
      const isError = /error|fail|fatal|exception|traceback/i.test(text);
      terminalWriteJob(text, isError ? "31" : "33");
    }
  }

  function appendJobEvents(events) {
    for (const event of events || []) appendJobEvent(event);
  }

  function applyJobPercent(percent) {
    if (percent === null || percent === undefined) return;
    setJobProgress(
      percent,
      `${actorLabel(state.jobActor)} ${state.jobKind} ${percent}%`,
    );
  }

  function resetJobState(kind, actor) {
    state.jobKind = kind || "job";
    state.jobActor = actor || "web";
    state.jobRunning = true;
    state.jobFinished = false;
    state.jobPercent = 0;
    state.lastTermPercent = -1;
  }

  function finishJob(job) {
    if (state.jobFinished && state.jobId === job.id) return;
    state.jobFinished = true;
    state.jobRunning = false;
    if (state.jobStream) {
      state.jobStream.close();
      state.jobStream = null;
    }
    const status =
      job.status === "ok"
        ? "完成"
        : job.status === "cancelled"
          ? "已取消"
          : "失败";
    $("jobStatus").textContent = status;
    if (job.status === "ok") {
      setJobProgress(
        100,
        `${actorLabel(job.actor || state.jobActor)} ${state.jobKind} 完成`,
      );
      terminalWriteJob("完成", "32");
      hideGlobalProgressSoon();
      toast(state.jobKind === "flash" ? "烧录完成" : "构建完成");
    } else {
      setJobProgress(
        state.jobPercent,
        `${actorLabel(job.actor || state.jobActor)} ${state.jobKind} ${job.status}`,
      );
      terminalWriteJob(job.error || status, "31");
      hideGlobalProgressSoon();
      toast(job.error || "任务失败", "error");
    }
    if (job.result && job.result.build_dir) {
      $("buildInput").value = job.result.build_dir;
    }
    updateConnectionUi();
    refreshSuggestions(false).catch(() => {});
    refreshStatus().catch(() => {});
  }

  async function attachJob(jobId, kind, actor) {
    if (state.jobId === jobId && (state.jobStream || state.jobAttaching)) {
      return;
    }
    if (state.jobStream) {
      state.jobStream.close();
      state.jobStream = null;
    }
    state.jobAttaching = true;
    state.jobId = jobId;
    resetJobState(kind, actor);
    $("jobStatus").textContent = "运行中";
    setJobProgress(0, `${actorLabel(state.jobActor)} ${state.jobKind} 0%`);
    terminalWriteJob(`${actorLabel(state.jobActor)} 开始`, "36");
    updateConnectionUi();

    let snapshot = null;
    try {
      snapshot = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    } catch {
      snapshot = null;
    }
    if (snapshot && snapshot.job) {
      const job = snapshot.job;
      state.jobActor = job.actor || state.jobActor;
      appendJobEvents(job.events);
      applyJobPercent(job.percent);
      if (TERMINAL_STATUSES.has(job.status)) {
        state.jobAttaching = false;
        finishJob(job);
        return;
      }
    }

    const stream = openSse(
      `/api/jobs/${encodeURIComponent(jobId)}/stream?since=0`,
      {
        onMessage: (payload) => {
          appendJobEvents(payload.events);
          applyJobPercent(payload.percent);
        },
        onError: () => {
          stream.close();
          state.jobStream = null;
          pollJob(jobId).catch(() => {});
        },
      },
    );
    stream.addEventListener("done", (message) => {
      const job = parseJson(message.data);
      stream.close();
      state.jobStream = null;
      if (job) finishJob(job);
    });
    state.jobStream = stream;
    state.jobAttaching = false;
  }

  async function pollJob(jobId) {
    let since = 0;
    for (;;) {
      const data = await api(
        `/api/jobs/${encodeURIComponent(jobId)}?since=${since}`,
      );
      const job = data.job;
      if (!job) return;
      state.jobActor = job.actor || state.jobActor;
      appendJobEvents(job.events);
      since = job.next || since;
      applyJobPercent(job.percent);
      if (TERMINAL_STATUSES.has(job.status)) {
        finishJob(job);
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
  }

  function handleJobEvent(event) {
    const data = event.data || {};
    if (event.kind === "job.start" && data.job_id) {
      if (state.jobId !== data.job_id) {
        attachJob(data.job_id, data.kind, event.actor).catch((error) =>
          toast(error.message, "error"),
        );
      }
      toast(`${actorLabel(event.actor)} 开始 ${data.kind || "任务"}`);
    }
    if (event.kind === "job.progress" && data.job_id === state.jobId) {
      if (data.percent !== null && data.percent !== undefined) {
        setJobProgress(
          data.percent,
          `${actorLabel(event.actor)} ${data.kind || state.jobKind} ${data.percent}%`,
        );
      }
    }
    if (event.kind === "job.done" && data.job_id === state.jobId) {
      finishJob({ ...data, id: data.job_id, actor: event.actor });
    }
  }

  // -- status / ports -------------------------------------------------

  function updateStatusbar() {
    $("statusPort").textContent = state.port || "—";
    $("statusBaud").textContent = state.baud ? String(state.baud) : "—";
    $("statusBytes").textContent = `RX ${state.nextSeq} / TX ${state.totalTx || 0}`;
    $("statusCursor").textContent = `cursor ${state.cursor}`;
    $("statusReconnect").textContent =
      `自动重连: ${state.autoReconnect ? "开" : "关"}` +
      (state.reconnecting ? " · 重连中" : "");
    $("statusServer").textContent = location.host;
  }

  function updateConnectionUi() {
    const flashJob = state.jobRunning && state.jobKind === "flash";
    const disabled = {
      connectBtn:
        state.connected || state.connecting || state.reconnecting || flashJob,
      disconnectBtn: (!state.connected && !state.reconnecting) || flashJob,
      resetBtn: !state.connected || flashJob,
      buildBtn: state.jobRunning,
      flashOnlyBtn: state.jobRunning,
      flashBuildBtn: state.jobRunning,
      projectInput: state.jobRunning,
      buildInput: state.jobRunning,
    };
    for (const [id, value] of Object.entries(disabled)) {
      $(id).disabled = value;
    }
    $("autoReconnect").checked = state.autoReconnect;

    const pill = $("statusPill");
    const text = $("statusText");
    if (state.reconnecting) {
      pill.dataset.state = "busy";
      text.textContent = "重连中…";
    } else if (flashJob) {
      pill.dataset.state = "busy";
      text.textContent = `烧录中 ${state.jobPercent}%`;
    } else if (state.connected) {
      pill.dataset.state = "open";
      text.textContent = "已连接";
    } else if (state.lastError) {
      pill.dataset.state = "error";
      text.textContent = "串口错误";
    } else {
      pill.dataset.state = "closed";
      text.textContent = "未连接";
    }
  }

  async function refreshStatus() {
    const data = await api("/api/status");
    const broker = data.broker || {};
    state.connected = Boolean(broker.open);
    state.reconnecting = Boolean(broker.reconnecting);
    state.autoReconnect = Boolean(broker.auto_reconnect);
    state.port = broker.port || state.port;
    state.baud = broker.baud || state.baud;
    state.firstSeq = Number(broker.first_seq) || 0;
    state.nextSeq = Number(broker.next_seq) || 0;
    state.totalTx = Number(broker.total_tx) || 0;
    state.lastError = broker.last_error || "";
    if (state.connected && !state.stream) {
      startSerialStream(Math.max(state.firstSeq, state.nextSeq - 64 * 1024));
    }
    if (!state.connected && !broker.wanted && state.stream) {
      stopSerialStream();
    }
    const logPath = broker.log_path || "";
    if (logPath) {
      const parts = logPath.split(/[\\/]/);
      const name = parts[parts.length - 2] || "";
      const link = $("downloadLog");
      link.href = `/api/logs/${encodeURIComponent(name)}/serial.log`;
      link.download = `${name}-serial.log`;
    }
    updateConnectionUi();
    updateStatusbar();
    return data;
  }

  function fillPortSelect(select, ports, preferred) {
    const previous = select.value;
    select.innerHTML = "";
    if (!ports.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "无串口";
      select.appendChild(option);
      return;
    }
    for (const item of ports) {
      const option = document.createElement("option");
      option.value = item.port;
      const description = item.description || item.device || "";
      option.textContent = description
        ? `${item.port} — ${description}`
        : item.port;
      select.appendChild(option);
    }
    let wanted = previous || preferred || state.port || "";
    if (!wanted) {
      const preferredPort = ports.find((item) =>
        /CH340|USB-SERIAL|CP210|FTDI|Silicon Labs/i.test(
          item.description || "",
        ),
      );
      wanted = preferredPort ? preferredPort.port : ports[0].port;
    }
    if (wanted && [...select.options].some((item) => item.value === wanted)) {
      select.value = wanted;
    } else {
      select.selectedIndex = 0;
    }
  }

  async function refreshPorts() {
    const data = await api("/api/ports");
    fillPortSelect($("portSelect"), data.ports || [], state.port);
  }

  function fillIfEmpty(input, value, force = false) {
    if (value === null || value === undefined) return;
    if (force || !input.value.trim()) {
      input.value = value;
    }
  }

  async function refreshSuggestions(force = false) {
    const data = await api("/api/suggest");
    fillIfEmpty($("projectInput"), data.project_dir || "", force);
    fillIfEmpty($("buildInput"), data.build_dir || "", force);
    if (force) {
      state.autoReconnect = Boolean(data.auto_reconnect);
      $("autoReconnect").checked = state.autoReconnect;
    }
    $("suggestTag").textContent = data.app ? `上次: ${data.app}` : "自动填充";
    updateStatusbar();
  }

  // -- connection ----------------------------------------------------

  async function connect() {
    if (state.connected || state.connecting) return;
    const port = $("portSelect").value;
    const baud = Number($("baudInput").value) || 1000000;
    if (!port) {
      toast("没有可用串口，先连接开发板", "error");
      return;
    }
    state.connecting = true;
    updateConnectionUi();
    try {
      await api("/api/open", { method: "POST", body: { port, baud } });
      term.reset();
      term.writeln(`\x1b[2m[host] 已连接 ${port} @ ${baud}\x1b[0m`);
      await refreshStatus();
      toast(`已连接 ${port}`);
    } catch (error) {
      toast(error.message, "error");
      await refreshStatus().catch(() => {});
    } finally {
      state.connecting = false;
      updateConnectionUi();
    }
  }

  async function disconnect() {
    try {
      await api("/api/close", { method: "POST" });
      stopSerialStream();
      state.connected = false;
      state.reconnecting = false;
      updateConnectionUi();
      term.writeln("\x1b[2m[host] 已断开\x1b[0m");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function sendRaw(text) {
    if (!state.connected || (state.jobRunning && state.jobKind === "flash")) {
      return;
    }
    try {
      await api("/api/send", {
        method: "POST",
        body: {
          data: text,
          encoding: "utf-8",
          line_ending: "none",
        },
      });
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function resetBoard() {
    if (!state.connected) return;
    try {
      await api("/api/reset", {
        method: "POST",
        body: { pulse_ms: 100 },
      });
      toast("已发送 RTS 复位脉冲");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  // -- build / flash --------------------------------------------------

  function deriveApp(projectDir) {
    const normalized = String(projectDir || "")
      .replace(/\\/g, "/")
      .split("/")
      .filter(Boolean);
    const index = normalized.lastIndexOf("sifli");
    if (
      index >= 0 &&
      normalized[index + 1] &&
      normalized[index + 2] === "project"
    ) {
      return normalized[index + 1];
    }
    return null;
  }

  function projectPayload(project) {
    return {
      app: deriveApp(project),
      project_dir: project || null,
    };
  }

  function flashPayload(buildFirst) {
    const project = $("projectInput").value.trim();
    return {
      ...projectPayload(project),
      build_dir: $("buildInput").value.trim() || null,
      build: Boolean(buildFirst),
      port: $("portSelect").value || state.port || null,
      baud: Number($("baudInput").value) || state.baud || null,
      verify: true,
      erase_all: false,
      reconnect: true,
    };
  }

  async function startJob(kind, payload) {
    if (state.jobRunning) return;
    const endpoint = kind === "flash" ? "/api/flash" : "/api/build";
    resetJobState(kind, "web");
    $("jobStatus").textContent = "提交中";
    setJobProgress(0, `WEB ${kind} 0%`);
    terminalWriteJob("提交 job...", "36");
    updateConnectionUi();
    try {
      const data = await api(endpoint, { method: "POST", body: payload });
      await attachJob(data.job_id, kind, "web");
    } catch (error) {
      state.jobRunning = false;
      state.jobFinished = true;
      $("jobStatus").textContent = "失败";
      terminalWriteJob(error.message, "31");
      hideGlobalProgressSoon();
      updateConnectionUi();
      toast(error.message, "error");
    }
  }

  async function runBuild() {
    const project = $("projectInput").value.trim();
    await startJob("build", projectPayload(project));
  }

  async function runFlash(buildFirst) {
    await startJob("flash", flashPayload(buildFirst));
  }

  // -- wiring ---------------------------------------------------------

  function onClick(id, handler) {
    $(id).addEventListener("click", (event) => {
      try {
        const result = handler(event);
        if (result && typeof result.catch === "function") {
          result.catch((error) => toast(error.message, "error"));
        }
      } catch (error) {
        toast(error.message, "error");
      }
    });
  }

  document.querySelectorAll(".tab[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  onClick("refreshPorts", refreshPorts);
  onClick("connectBtn", connect);
  onClick("disconnectBtn", disconnect);
  onClick("resetBtn", resetBoard);
  onClick("clearBtn", () => term.clear());
  onClick("downloadLog", (event) => {
    const href = $("downloadLog").getAttribute("href");
    if (!href || href === "#") {
      event.preventDefault();
      toast("当前还没有串口日志");
    }
  });
  onClick("buildBtn", runBuild);
  onClick("flashOnlyBtn", () => runFlash(false));
  onClick("flashBuildBtn", () => runFlash(true));

  $("localEcho").addEventListener("change", () => {
    try {
      localStorage.setItem(
        "sifli.localEcho",
        $("localEcho").checked ? "1" : "0",
      );
    } catch {
      /* ignore storage errors */
    }
  });

  $("autoReconnect").addEventListener("change", async () => {
    const enabled = $("autoReconnect").checked;
    state.autoReconnect = enabled;
    try {
      await api("/api/serial/auto_reconnect", {
        method: "POST",
        body: { enabled },
      });
      if (enabled && !state.connected) {
        await connect();
      }
      updateStatusbar();
      updateConnectionUi();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  // RT-Thread finsh ends a line on CR alone. Sending CRLF makes it handle
  // both characters and print the `msh />` prompt twice, so keep Enter as CR.
  term.onData((data) => {
    if (!state.connected || (state.jobRunning && state.jobKind === "flash")) {
      return;
    }
    if ($("localEcho").checked) {
      if (data === "\r") {
        term.write("\r\n");
      } else if (data === "\x7f") {
        term.write("\b \b");
      } else if (data === "\t" || data >= " ") {
        term.write(data);
      }
    }
    void sendRaw(data);
  });

  // Chinese IMEs commit a composition with Space; some browsers report that
  // confirmation as an Enter keydown, which xterm would forward as CR and the
  // board would answer with an extra `msh />` prompt per keystroke. Swallow
  // Enter while composing and right after a composition ends.
  let lastCompositionEnd = 0;
  if (term.textarea) {
    term.textarea.addEventListener("compositionend", () => {
      lastCompositionEnd = performance.now();
    });
  }
  term.attachCustomKeyEventHandler((event) => {
    if (event.keyCode !== 13) return true;
    if (event.type === "keypress") return false;
    if (event.type !== "keydown") return true;
    if (event.isComposing) return false;
    if (performance.now() - lastCompositionEnd < 100) return false;
    return true;
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "l") {
      event.preventDefault();
      term.clear();
    }
  });

  window.addEventListener("resize", () => {
    window.requestAnimationFrame(fitTerminal);
  });
  if ("ResizeObserver" in window) {
    new ResizeObserver(() => {
      window.requestAnimationFrame(fitTerminal);
    }).observe($("terminal"));
  }
  window.addEventListener("beforeunload", () => {
    stopSerialStream();
    if (state.eventsStream) state.eventsStream.close();
    if (state.jobStream) state.jobStream.close();
  });

  const initialTab = location.hash.slice(1);
  if (["terminal", "activity"].includes(initialTab)) {
    switchTab(initialTab);
  }
  window.requestAnimationFrame(fitTerminal);

  async function boot() {
    await refreshPorts();
    await refreshSuggestions(true);
    await refreshStatus();
    await loadActivityHistory();
    // Attach a job that was already running before the page reloaded.
    const data = await api("/api/jobs");
    const running = (data.jobs || []).find(
      (job) => job.status === "running" || job.status === "queued",
    );
    if (running) {
      await attachJob(running.id, running.kind, running.actor);
    }
  }

  boot().catch((error) => toast(error.message, "error"));

  window.setInterval(() => {
    refreshStatus().catch(() => {});
  }, 1500);
})();
