/* Standalone flasher UI shared by the ESP32 (esptool) and SiFli (sftool)
 * hosts.  Everything board-specific comes from /api/flash/env; this file only
 * renders the capability list and talks to the small flash API. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const JOB_KEY = "flasher.job";
  const LOG_LIMIT = 1200;

  const state = {
    env: null,
    plan: null,
    planId: "",
    jobId: "",
    running: false,
    stream: null,
    percent: 0,
    log: [],
    envRendered: false,
    lastError: "",
    lastSeq: 0,
  };

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok || (payload && payload.ok === false)) {
      const message =
        (payload && (payload.message || payload.error)) ||
        `HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.code = payload && payload.error;
      error.payload = payload;
      throw error;
    }
    return payload || {};
  }

  const post = (path, body) =>
    api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });

  let toastTimer = null;

  function toast(message, type = "ok") {
    const node = $("toast");
    node.textContent = message;
    node.className = `toast show${type === "error" ? " error" : ""}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      node.className = "toast";
    }, 3200);
  }

  function setBanner(message, type = "") {
    const node = $("banner");
    if (!message) {
      node.className = "banner hidden";
      node.textContent = "";
      return;
    }
    node.textContent = message;
    node.className = `banner${type === "error" ? " error" : ""}`;
  }

  async function withBusy(button, fn) {
    if (!button) return fn();
    const disabled = button.disabled;
    button.disabled = true;
    button.classList.add("busy");
    try {
      return await fn();
    } finally {
      button.classList.remove("busy");
      button.disabled = disabled;
    }
  }

  function formatBytes(value) {
    const size = Number(value) || 0;
    if (size >= 1024 * 1024) return `${(size / 1048576).toFixed(1)} MB`;
    if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${size} B`;
  }

  function formatAddress(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "number") {
      return `0x${value.toString(16).toUpperCase()}`;
    }
    const text = String(value);
    return text.startsWith("0x") ? text : `0x${text}`;
  }

  // --------------------------------------------------------------- backend

  function hasSource(name) {
    const sources = (state.env && state.env.sources) || [];
    return sources.includes(name);
  }

  function backendInfo() {
    const env = state.env || {};
    const backend = env.backend || {};
    if (backend.kind || backend.name || backend.found !== undefined) {
      return backend;
    }
    const legacy = env.esptool || {};
    return {
      kind: "esptool",
      name: "esptool",
      version: legacy.version || "",
      label: legacy.label || "",
      found: Boolean(legacy.found),
      chip: "ESP32-C6",
      board: "esp32c6",
    };
  }

  function backendReady() {
    const env = state.env || {};
    return Boolean(env.fake || backendInfo().found);
  }

  function renderBackend() {
    const env = state.env || {};
    const backend = backendInfo();
    const ready = backendReady();
    const name = backend.name || backend.kind || "unknown";
    const version = backend.version || "";
    const chip = backend.chip || "";
    const fake = Boolean(env.fake);

    $("backendDot").className = `dot ${ready ? "on" : ""}`;
    $("backendName").textContent = ready ? name : `${name} 未找到`;
    $("backendVersion").textContent = version ? `v${version}` : "";
    $("backendChip").title = backend.label || env.hint || "";

    $("heroSub").textContent = [
      `${name}${version ? " " + version : ""}`,
      chip,
      fake ? "模拟烧录" : "真实烧录",
    ]
      .filter(Boolean)
      .join(" · ");

    $("backendMark").textContent = (name || "?").slice(0, 1);
    $("backendTitle").textContent = `${name}${version ? " " + version : ""}`;
    $("backendMeta").textContent = [chip, backend.board].filter(Boolean).join(" · ") || "—";
    $("backendTag").textContent = fake ? "模拟" : ready ? "就绪" : "未找到";
    $("backendTag").className = `tag ${fake ? "warn" : ready ? "ok" : "bad"}`;

    const rows = [
      ["类型", backend.kind || "—"],
      ["版本", version || "—"],
      ["芯片", chip || "—"],
      ["板卡", backend.board || "—"],
      ["路径", backend.label || "—"],
      ["模式", fake ? "模拟（不占用串口）" : "真实烧录"],
    ];
    $("backendKv").innerHTML = rows
      .map(
        ([key, value]) =>
          `<dt>${esc(key)}</dt><dd title="${esc(value)}">${esc(value)}</dd>`,
      )
      .join("");

    const hint = env.hint || backend.hint || "";
    $("backendHint").textContent =
      hint ||
      "同一个烧录页由不同 host 提供不同后端：ESP32 host 用 esptool，SiFli host 用 sftool。";
    $("footMeta").textContent = `${name}${version ? " " + version : ""} · ${location.host}`;

    if (!ready && hint) {
      setBanner(hint, "error");
    } else if (!ready) {
      setBanner(`${name} 未就绪；请先安装或配置后端。`, "error");
    } else {
      setBanner("");
    }
  }

  // ------------------------------------------------------------------ env

  function fillSelect(select, values, selected) {
    const previous = selected == null ? select.value : String(selected);
    select.innerHTML = values
      .map(
        (item) =>
          `<option value="${esc(item.value)}">${esc(item.label)}</option>`,
      )
      .join("");
    if (previous && values.some((item) => String(item.value) === previous)) {
      select.value = previous;
    }
  }

  function renderOptions() {
    const env = state.env || {};
    const options = env.options || {};
    const after = options.after || ["hard_reset", "soft_reset", "no_reset"];
    const before = options.before || [];
    const labels = {
      hard_reset: "硬复位",
      soft_reset: "软复位",
      no_reset: "不复位",
      no_reset_stub: "不复位（stub）",
      default_reset: "默认（自动）",
      usb_reset: "USB 复位",
    };

    if (!state.envRendered) {
      const bauds = env.baud_rates || [115200, 230400, 460800, 921600];
      const baud = Number(env.default_baud) || bauds[0];
      fillSelect(
        $("baudSelect"),
        bauds.map((value) => ({ value, label: String(value) })),
        baud,
      );
    }

    const currentAfter = $("afterSelect").value;
    fillSelect(
      $("afterSelect"),
      after.map((value) => ({ value, label: labels[value] || value })),
      currentAfter || env.defaults?.after || after[0],
    );

    const beforeRow = $("beforeRow");
    if (before.length) {
      beforeRow.classList.remove("hidden");
      const currentBefore = $("beforeSelect").value;
      fillSelect(
        $("beforeSelect"),
        before.map((value) => ({ value, label: labels[value] || value })),
        currentBefore || before[0],
      );
    } else {
      beforeRow.classList.add("hidden");
    }

    $("eraseRow").classList.toggle("hidden", options.erase_all === false);
    $("verifyRow").classList.toggle("hidden", options.verify === false);
    $("reconnectRow").classList.toggle("hidden", options.reconnect === false);
    const verifySupported = options.verify_supported !== false;
    $("verify").disabled = !verifySupported;
    $("verify").title = verifySupported
      ? ""
      : "当前后端始终校验，没有单独开关";
    syncReconnect();
  }

  function renderSources() {
    const env = state.env || {};
    const blocks = {
      upload: $("uploadBlock"),
      path: $("pathBlock"),
      build_dir: $("buildBlock"),
      project: $("projectBlock"),
    };
    for (const [name, node] of Object.entries(blocks)) {
      node.classList.toggle("hidden", !hasSource(name));
    }

    const labels = {
      upload: "上传",
      path: "服务器路径",
      build_dir: "构建目录",
      project: "工程目录",
    };
    const active = Object.entries(labels)
      .filter(([name]) => hasSource(name))
      .map(([, label]) => label);
    $("sourceTag").textContent = active.length ? active.join(" · ") : "未配置";

    const defaults = env.defaults || {};
    if (!$("pathInput").value && defaults.path) {
      $("pathInput").value = defaults.path;
    }
    if (!$("buildInput").value && defaults.build_dir) {
      $("buildInput").value = defaults.build_dir;
    }
    if (!$("projectInput").value && defaults.project_dir) {
      $("projectInput").value = defaults.project_dir;
    }
    if (!$("appInput").value && defaults.app) {
      $("appInput").value = defaults.app;
    }

    const hint = env.source_hint || "";
    if (hint) $("sourceHint").textContent = hint;
  }

  function renderSuggestions() {
    const env = state.env || {};
    const items = env.suggestions || [];
    const node = $("suggestions");
    node.innerHTML = items
      .map((item) => {
        let source = null;
        if (item.source && typeof item.source === "object") {
          source = item.source;
        } else if (item.build_dir) {
          source = { build_dir: item.build_dir };
        } else if (item.path) {
          source = { path: item.path };
        } else if (item.app || item.project_dir) {
          source = {
            app: item.app || "",
            project_dir: item.project_dir || "",
          };
        }
        if (!source) return "";
        const encoded = encodeURIComponent(JSON.stringify(source));
        return `<button class="ghost small" type="button" data-source="${encoded}">${esc(item.label || "使用建议")}</button>`;
      })
      .join("");
  }

  function renderEnv() {
    const env = state.env || {};
    renderBackend();
    renderSources();
    renderSuggestions();
    renderOptions();
    state.envRendered = true;
    updateStartState();
  }

  async function loadEnv() {
    try {
      const data = await api("/api/flash/env");
      state.env = data.env || {};
    } catch (error) {
      state.env = null;
      setBanner(error.message, "error");
    }
    if (state.env) {
      renderEnv();
    } else {
      $("heroSub").textContent = "无法读取烧录环境";
      $("backendDot").className = "dot";
      $("backendName").textContent = "环境不可用";
      $("backendTag").textContent = "错误";
      $("backendTag").className = "tag bad";
    }
  }

  // ----------------------------------------------------------------- ports

  async function loadPorts() {
    try {
      const data = await api("/api/ports");
      const ports = data.ports || [];
      const previous =
        $("portSelect").value ||
        (state.env && state.env.defaults && state.env.defaults.port) ||
        "";
      const options = ports.map((item) => {
        const label = `${item.port}${item.description ? " · " + item.description : ""}`;
        return `<option value="${esc(item.port)}">${esc(label)}</option>`;
      });
      $("portSelect").innerHTML = [
        '<option value="">选择串口</option>',
        ...options,
      ].join("");
      if (previous && ports.some((item) => item.port === previous)) {
        $("portSelect").value = previous;
      } else {
        $("portSelect").value = "";
      }
      if (!ports.length) {
        $("portSelect").innerHTML = '<option value="">未发现串口</option>';
      }
    } catch (error) {
      $("portSelect").innerHTML = '<option value="">读取串口失败</option>';
    }
    updateStartState();
  }

  // ------------------------------------------------------------------ plan

  function renderPlan() {
    const plan = state.plan;
    const body = $("planBody");
    if (!plan) {
      state.planId = "";
      body.innerHTML =
        '<tr><td colspan="3" class="empty">尚未解析固件</td></tr>';
      $("planTag").textContent = "未选择";
      $("planTag").className = "tag";
      $("planHint").textContent = "选择固件后会显示地址映射。";
      $("planTotal").textContent = "";
      $("chipTag").textContent = "—";
      updateStartState();
      return;
    }

    state.planId = plan.plan_id;
    const entries = plan.entries || [];
    body.innerHTML = entries.length
      ? entries
          .map(
            (entry) =>
              `<tr><td>${esc(entry.name)}</td><td><code>${esc(formatAddress(entry.address))}</code></td><td>${formatBytes(entry.size)}</td></tr>`,
          )
          .join("")
      : '<tr><td colspan="3" class="empty">计划为空</td></tr>';

    $("planTag").textContent = plan.notes || plan.source || "已解析";
    $("planTag").className = "tag ok";
    $("planHint").textContent = `${entries.length} 个文件${
      plan.notes ? " · " + plan.notes : ""
    }`;
    const total = entries.reduce((sum, entry) => sum + (Number(entry.size) || 0), 0);
    $("planTotal").textContent = `合计 ${formatBytes(total)}`;
    const chip = [plan.chip, plan.memory].filter(Boolean).join(" · ");
    $("chipTag").textContent = chip || "—";
    updateStartState();
  }

  async function planSource(source, button) {
    if (state.running) return;
    if (source.path && $("pathInput")) $("pathInput").value = source.path;
    if (source.build_dir && $("buildInput")) {
      $("buildInput").value = source.build_dir;
    }
    if (source.project_dir && $("projectInput")) {
      $("projectInput").value = source.project_dir;
    }
    if (source.app && $("appInput")) $("appInput").value = source.app;
    state.plan = null;
    state.lastError = "";
    renderPlan();
    setBanner("");
    await withBusy(button, async () => {
      try {
        const data = await post("/api/flash/plan", source);
        state.plan = data;
        renderPlan();
        toast(`已解析 ${(data.entries || []).length} 个文件`);
      } catch (error) {
        state.lastError = error.message;
        setBanner(error.message, "error");
        toast(error.message, "error");
      }
    });
  }

  function planFromPath() {
    const path = $("pathInput").value.trim();
    if (!path) {
      toast("请输入固件路径", "error");
      return;
    }
    planSource({ path }, $("pathPlan"));
  }

  function planFromBuild() {
    const buildDir = $("buildInput").value.trim();
    if (!buildDir) {
      toast("请输入构建目录", "error");
      return;
    }
    planSource({ build_dir: buildDir }, $("buildPlan"));
  }

  function planFromProject() {
    const app = $("appInput").value.trim();
    const projectDir = $("projectInput").value.trim();
    if (!app && !projectDir) {
      toast("请输入应用名或工程目录", "error");
      return;
    }
    const source = {};
    if (app) source.app = app;
    if (projectDir) source.project_dir = projectDir;
    planSource(source, $("projectPlan"));
  }

  function uploadFile(file) {
    if (!file || state.running) return;
    if (!/\.(bin|zip)$/i.test(file.name)) {
      toast("只支持 .bin 或 .zip", "error");
      return;
    }
    const wrap = $("uploadWrap");
    const bar = $("uploadBar");
    wrap.classList.remove("hidden");
    bar.style.width = "0%";
    $("uploadHint").textContent = `上传 ${file.name} · ${formatBytes(file.size)}…`;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/flash/upload?name=${encodeURIComponent(file.name)}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        bar.style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
      }
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (error) {
        data = null;
      }
      if (!data || !data.ok) {
        const message = data ? data.message || data.error : "上传失败";
        $("uploadHint").textContent = message;
        toast(message, "error");
        wrap.classList.add("hidden");
        return;
      }
      bar.style.width = "100%";
      $("uploadHint").textContent = `${data.name} · ${formatBytes(data.size)} · 已解析`;
      planSource({ token: data.token }, null);
    };
    xhr.onerror = () => {
      $("uploadHint").textContent = "上传失败（网络错误）";
      toast("上传失败", "error");
      wrap.classList.add("hidden");
    };
    xhr.send(file);
  }

  // -------------------------------------------------------------- job state

  function syncReconnect() {
    const noReset = $("afterSelect").value === "no_reset";
    const row = $("reconnectRow");
    if (!row || row.classList.contains("hidden")) return;
    $("reconnect").disabled = noReset || state.running;
    if (noReset) $("reconnect").checked = false;
  }

  function updateProgress(percent) {
    const value = Math.max(0, Math.min(100, Number(percent) || 0));
    state.percent = value;
    $("progressBar").style.width = `${value}%`;
    $("percentText").textContent = `${value}%`;
    $("progressBar").parentElement.setAttribute("aria-valuenow", String(value));
  }

  function setJobStatus(status, error) {
    const labels = {
      queued: "排队",
      running: "烧录中",
      ok: "完成",
      failed: "失败",
      cancelled: "已取消",
    };
    const node = $("jobStatus");
    node.textContent = labels[status] || status || "空闲";
    node.className = `status-tag ${
      status === "ok"
        ? "ok"
        : status === "failed"
          ? "failed"
          : status === "running" || status === "queued"
            ? "running"
            : ""
    }`;
    if (status === "running") {
      $("progressText").textContent = "正在写入…";
    } else if (status === "queued") {
      $("progressText").textContent = "已排队，等待串口…";
    } else if (status === "ok") {
      $("progressText").textContent = "烧录完成";
    } else if (status === "cancelled") {
      $("progressText").textContent = "烧录已取消；设备可能需要复位";
    } else if (status === "failed") {
      $("progressText").textContent = error || state.lastError || "烧录失败";
    } else {
      $("progressText").textContent = "等待开始";
    }
  }

  function setLocked(locked) {
    const ids = [
      "fileInput",
      "pathInput",
      "pathPlan",
      "buildInput",
      "buildPlan",
      "appInput",
      "projectInput",
      "projectPlan",
      "portSelect",
      "portRefresh",
      "baudSelect",
      "eraseAll",
      "afterSelect",
      "beforeSelect",
    ];
    for (const id of ids) {
      const node = $(id);
      if (node) node.disabled = locked;
    }
    $("verify").disabled = locked || state.env?.options?.verify_supported === false;
    $("reconnect").disabled = locked || $("afterSelect").value === "no_reset";
    for (const button of $("suggestions").querySelectorAll("button")) {
      button.disabled = locked;
    }
    $("dropZone").classList.toggle("disabled", locked);
  }

  function updateStartState() {
    const ready = backendReady();
    const port = $("portSelect").value;
    const why = !state.planId
      ? "先选择并解析固件"
      : state.running
        ? "烧录进行中"
        : !ready
          ? "后端未就绪"
          : !port
            ? "请选择串口"
            : "";
    $("startBtn").disabled = Boolean(why);
    $("startBtn").title = why;
    $("cancelBtn").disabled = !state.running || !state.jobId;
  }

  function setRunning(status, percent, error) {
    state.running = status === "queued" || status === "running";
    setJobStatus(status, error);
    updateProgress(percent);
    setLocked(state.running);
    updateStartState();
  }

  // ------------------------------------------------------------------- log

  function renderLog() {
    const node = $("log");
    node.textContent = state.log.join("\n");
    if ($("autoscroll").checked) {
      node.scrollTop = node.scrollHeight;
    }
  }

  function appendLog(lines) {
    for (const line of lines || []) {
      if (line === undefined || line === null || line === "") continue;
      state.log.push(String(line));
    }
    if (state.log.length > LOG_LIMIT) {
      state.log.splice(0, state.log.length - LOG_LIMIT);
    }
    renderLog();
  }

  function appendJobEvents(events) {
    const lines = [];
    for (const item of events || []) {
      const seq = Number(item.seq) || 0;
      if (seq && seq <= state.lastSeq) continue;
      if (seq) state.lastSeq = seq;
      lines.push(item.stream === "stderr" ? `! ${item.text}` : item.text);
    }
    appendLog(lines);
  }

  // ------------------------------------------------------------------- job

  function closeStream() {
    if (state.stream) {
      state.stream.close();
      state.stream = null;
    }
  }

  function finishJob(job) {
    closeStream();
    state.jobId = "";
    sessionStorage.removeItem(JOB_KEY);
    appendJobEvents(job.events);
    state.lastError = job.error || "";
    setRunning(job.status, job.percent, job.error);
    if (job.status === "ok") {
      toast("烧录完成");
    } else if (job.status === "cancelled") {
      toast("烧录已取消");
    } else {
      toast(job.error || "烧录失败", "error");
    }
    loadEnv();
    loadPorts();
  }

  function attachJob(jobId, since = 0) {
    closeStream();
    state.jobId = jobId;
    state.lastSeq = Math.max(0, Number(since) || 0);
    sessionStorage.setItem(JOB_KEY, jobId);
    const stream = new EventSource(
      `/api/jobs/${encodeURIComponent(jobId)}/stream?since=${state.lastSeq}`,
    );
    state.stream = stream;
    stream.onmessage = (event) => {
      let data = null;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      if (Array.isArray(data.events)) {
        appendJobEvents(data.events);
      }
      if (data.status) {
        setRunning(data.status, data.percent);
      }
    };
    stream.addEventListener("done", (event) => {
      try {
        finishJob(JSON.parse(event.data));
      } catch (error) {
        closeStream();
        setRunning("failed", state.percent, "任务结束但回执无法解析");
      }
    });
    stream.onerror = async () => {
      if (!state.jobId) return;
      try {
        const data = await api(
          `/api/jobs/${encodeURIComponent(state.jobId)}?since=0`,
        );
        const job = data.job || {};
        if (job.status && ["ok", "failed", "cancelled"].includes(job.status)) {
          finishJob(job);
          return;
        }
        if (job.status) setRunning(job.status, job.percent);
      } catch (error) {
        // EventSource retries on its own; keep the stream open while running.
      }
      if (!state.running) {
        closeStream();
      }
    };
  }

  async function restoreJob() {
    const saved = sessionStorage.getItem(JOB_KEY);
    if (saved) {
      try {
        const data = await api(`/api/jobs/${encodeURIComponent(saved)}?since=0`);
        const job = data.job || {};
        if (["queued", "running"].includes(job.status)) {
          state.lastSeq = 0;
          appendJobEvents(job.events);
          setRunning(job.status, job.percent);
          attachJob(saved, state.lastSeq);
          return;
        }
        sessionStorage.removeItem(JOB_KEY);
      } catch (error) {
        sessionStorage.removeItem(JOB_KEY);
      }
    }
    try {
      const data = await api("/api/jobs");
      const job = (data.jobs || []).find(
        (item) =>
          item.kind === "flash" &&
          (item.status === "running" || item.status === "queued"),
      );
      if (!job) return;
      setRunning(job.status, job.percent);
      attachJob(job.id);
    } catch (error) {
      // Listing jobs is a convenience; ignore when a host does not expose it.
    }
  }

  async function startFlash() {
    if (!state.planId || state.running) return;
    const port = $("portSelect").value;
    if (!port) {
      toast("请选择串口", "error");
      return;
    }
    const payload = {
      plan_id: state.planId,
      port,
      baud: Number($("baudSelect").value) || undefined,
      erase_all: $("eraseAll").checked,
      verify: $("verify").checked,
      after: $("afterSelect").value || undefined,
      reconnect: $("reconnect").checked,
    };
    if (!$("beforeRow").classList.contains("hidden")) {
      payload.before = $("beforeSelect").value || undefined;
    }
    setBanner("");
    await withBusy($("startBtn"), async () => {
      try {
        let data;
        try {
          data = await post("/api/flash/start", payload);
        } catch (error) {
          // Older hosts only expose /api/flash; keep the page portable.
          if (error.status !== 404) throw error;
          data = await post("/api/flash", payload);
        }
        state.log = [];
        renderLog();
        setRunning("running", 0);
        attachJob(data.job_id);
        toast("烧录已开始");
      } catch (error) {
        state.lastError = error.message;
        setBanner(error.message, "error");
        toast(error.message, "error");
      }
    });
  }

  async function cancelFlash() {
    if (!state.jobId) return;
    try {
      await post(`/api/jobs/${encodeURIComponent(state.jobId)}/cancel`);
      toast("已请求取消");
    } catch (error) {
      toast(error.message, "error");
    }
  }

  // ---------------------------------------------------------------- events

  function bindEvents() {
    $("envRefresh").addEventListener("click", async () => {
      await loadEnv();
      await loadPorts();
      toast("环境已刷新");
    });

    $("fileInput").addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      uploadFile(file);
      event.target.value = "";
    });

    $("dropZone").addEventListener("click", () => {
      if (!state.running) $("fileInput").click();
    });
    $("dropZone").addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (!state.running) $("fileInput").click();
      }
    });
    for (const name of ["dragenter", "dragover"]) {
      $("dropZone").addEventListener(name, (event) => {
        event.preventDefault();
        $("dropZone").classList.add("over");
      });
    }
    for (const name of ["dragleave", "drop"]) {
      $("dropZone").addEventListener(name, (event) => {
        event.preventDefault();
        $("dropZone").classList.remove("over");
      });
    }
    $("dropZone").addEventListener("drop", (event) => {
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      uploadFile(file);
    });

    $("pathPlan").addEventListener("click", planFromPath);
    $("buildPlan").addEventListener("click", planFromBuild);
    $("projectPlan").addEventListener("click", planFromProject);
    $("pathInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter") planFromPath();
    });
    $("buildInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter") planFromBuild();
    });

    $("suggestions").addEventListener("click", (event) => {
      const button = event.target.closest("[data-source]");
      if (!button) return;
      try {
        const source = JSON.parse(decodeURIComponent(button.dataset.source));
        planSource(source, button);
      } catch (error) {
        toast("建议项无法解析", "error");
      }
    });

    $("portRefresh").addEventListener("click", loadPorts);
    $("startBtn").addEventListener("click", startFlash);
    $("cancelBtn").addEventListener("click", cancelFlash);
    $("afterSelect").addEventListener("change", syncReconnect);

    $("logClear").addEventListener("click", () => {
      state.log = [];
      renderLog();
    });
    $("logDownload").addEventListener("click", () => {
      const blob = new Blob([state.log.join("\n") + "\n"], {
        type: "text/plain;charset=utf-8",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `flash-${Date.now()}.log`;
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }

  async function boot() {
    bindEvents();
    await loadEnv();
    await loadPorts();
    await restoreJob();
    renderLog();
  }

  boot();
})();
