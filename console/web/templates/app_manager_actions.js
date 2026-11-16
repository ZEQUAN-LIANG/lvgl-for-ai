  function managerError(result) {
    if (result.status === 0) return "无法连接本地服务";
    if (result.data && result.data.error && result.data.error.message) {
      return result.data.error.message;
    }
    return "HTTP " + result.status;
  }

  async function managerCall(method, path, body) {
    try {
      const options = { method: method, cache: "no-store", headers: {} };
      if (body !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.headers["X-LVGL-AI-Request"] = "1";
        options.body = JSON.stringify(body);
      }
      const response = await fetch(path, options);
      let data = null;
      try { data = await response.json(); } catch (error) { data = null; }
      return { ok: response.ok, status: response.status, data: data };
    } catch (error) {
      return { ok: false, status: 0, data: null };
    }
  }

  function setManagerStatus(text) {
    if (managerStatus) managerStatus.textContent = text || "";
  }

  function makeNode(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function addBadge(parent, text, kind) {
    const badge = makeNode("span", "manager-badge", text);
    if (kind) badge.classList.add(kind);
    parent.appendChild(badge);
  }

  function addAction(parent, label, handler, locked) {
    const button = makeNode("button", "ghost-btn", label);
    button.type = "button";
    button.dataset.mutation = "1";
    if (locked) button.dataset.locked = "1";
    button.addEventListener("click", handler);
    parent.appendChild(button);
    return button;
  }

  function openAppManager() {
    if (!appManager) return;
    if (typeof appManager.showModal === "function") {
      if (!appManager.open) appManager.showModal();
    } else {
      appManager.setAttribute("open", "");
    }
    loadManager();
  }

  function closeAppManager() {
    if (!appManager) return;
    if (typeof appManager.close === "function" && appManager.open) {
      appManager.close();
    } else {
      appManager.removeAttribute("open");
    }
  }

  async function loadManager() {
    const token = ++managerToken;
    setManagerStatus("读取中…");
    const result = await managerCall("GET", "/api/apps");
    if (token !== managerToken) return;
    if (!result.ok || !result.data) {
      setManagerStatus("未完成：" + managerError(result));
      return;
    }
    managerApps = {};
    (result.data.apps || []).forEach(function (app) {
      managerApps[app.name] = app;
    });
    renderManager(result.data);
    setManagerStatus("");
  }

  function renderManager(data) {
    if (managerRoots) {
      const roots = data.roots || {};
      managerRoots.textContent =
        "应用代码 " + (roots.app || "apps") + "/<应用>/ · 场景 " +
        (roots.scenarios || "scenarios") + " · 注册 " +
        (roots.app_c || "user/app/app.c") + " · 回收站 " +
        (roots.trash || ".trash/apps") + "/<id>/";
    }
    renderAppList(data.apps || [], data.orphans || [], data.warnings || []);
    renderTrash(data.trash || []);
    renderRecent(data.recent || []);
    renderLastOperation(data.last_operation || null);
    updateManagerAvailability(liveStarting, liveRunning);
  }

  function renderAppList(apps, orphans, warnings) {
    if (!managerList) return;
    managerList.textContent = "";
    if (!apps.length && !orphans.length) {
      managerList.appendChild(makeNode("p", "manager-empty", "还没有应用。"));
    }
    apps.forEach(function (app) {
      const item = makeNode("div", "manager-item");
      const head = makeNode("div", "manager-item-head");
      head.appendChild(makeNode("span", "manager-name", app.name));
      if (app.default) addBadge(head, "默认", "is-accent");
      if (app.protected) addBadge(head, "保护");
      if (!app.app_dir_exists) addBadge(head, "目录缺失", "is-warn");
      if (!app.scenario_files.length) addBadge(head, "无场景", "is-warn");
      item.appendChild(head);
      const meta = makeNode("div", "manager-meta",
        (app.app_dir || "") +
        (app.scenario_files.length ? " · " + app.scenario_files.join(", ") : "") +
        (app.modified ? " · " + app.modified : ""));
      item.appendChild(meta);
      if (app.warnings && app.warnings.length) {
        item.appendChild(makeNode("div", "manager-meta", app.warnings.join("；")));
      }
      const actions = makeNode("div", "manager-actions");
      addAction(actions, "目录结构", function () { showManagedTree(app.name); });
      addAction(actions, "预览", function () { previewManagedApp(app.name); },
        !app.scenario_files.length);
      addAction(actions, "删除", function () { deleteManagedApp(app.name); },
        !app.deletable);
      item.appendChild(actions);
      managerList.appendChild(item);
    });
    orphans.forEach(function (orphan) {
      const item = makeNode("div", "manager-item");
      const head = makeNode("div", "manager-item-head");
      head.appendChild(makeNode("span", "manager-name", orphan.name || "未知"));
      addBadge(head, "未注册", "is-warn");
      item.appendChild(head);
      item.appendChild(makeNode("div", "manager-meta", orphan.path || ""));
      managerList.appendChild(item);
    });
    warnings.forEach(function (warning) {
      managerList.appendChild(makeNode("p", "manager-empty", warning));
    });
  }

  function renderTrash(entries) {
    if (!managerTrash) return;
    managerTrash.textContent = "";
    if (!entries.length) {
      managerTrash.appendChild(makeNode("p", "manager-empty", "回收站是空的。"));
      return;
    }
    entries.forEach(function (entry) {
      const item = makeNode("div", "manager-item");
      const head = makeNode("div", "manager-item-head");
      head.appendChild(makeNode("span", "manager-name", entry.name || entry.trash_id));
      if (!entry.valid) addBadge(head, "无法读取", "is-warn");
      item.appendChild(head);
      item.appendChild(makeNode("div", "manager-meta",
        entry.trash_id +
        (entry.deleted_at ? " · " + entry.deleted_at : "") +
        (entry.scenario_files && entry.scenario_files.length
          ? " · " + entry.scenario_files.join(", ") : "")));
      const actions = makeNode("div", "manager-actions");
      addAction(actions, "恢复", function () {
        restoreTrashedApp(entry.trash_id);
      }, !entry.valid);
      addAction(actions, "永久删除", function () {
        purgeTrashedApp(entry.trash_id, entry.name || entry.trash_id);
      });
      item.appendChild(actions);
      managerTrash.appendChild(item);
    });
  }

  function renderRecent(items) {
    if (!managerRecent) return;
    managerRecent.textContent = "";
    if (!items.length) {
      managerRecent.appendChild(makeNode("li", "", "还没有记录。"));
      return;
    }
    items.forEach(function (item) {
      const li = document.createElement("li");
      const code = makeNode("code", "", item.path || "");
      li.appendChild(code);
      li.appendChild(document.createTextNode(
        " · " + (item.modified || "") + " · " + (item.kind || "")
      ));
      managerRecent.appendChild(li);
    });
  }

  function renderLastOperation(operation) {
    if (!managerLast) return;
    if (!operation) {
      managerLast.textContent = "还没有操作记录。";
      return;
    }
    const labels = {
      create: "新建",
      delete: "移入回收站",
      restore: "恢复",
      purge: "永久删除"
    };
    const details = [];
    ["created", "updated", "scenarios"].forEach(function (key) {
      if (Array.isArray(operation[key])) {
        operation[key].forEach(function (value) { details.push(value); });
      }
    });
    if (operation.path) details.push(operation.path);
    if (operation.trash_dir) details.push(operation.trash_dir);
    managerLast.textContent =
      (labels[operation.action] || operation.action || "操作") + " " +
      (operation.name || operation.trash_id || "") +
      (operation.at ? " · " + operation.at : "") +
      (details.length ? " · " + details.join(", ") : "");
  }

  function renderTreeNode(node) {
    const li = document.createElement("li");
    li.title = node.path || "";
    const label = makeNode(
      "span",
      node.type === "dir" ? "tree-dir" : (node.type === "link" ? "tree-link" : ""),
      node.name + (node.type === "dir" ? "/" : "")
    );
    li.appendChild(label);
    if (node.size !== null && node.size !== undefined) {
      li.appendChild(document.createTextNode(" · " + node.size));
    }
    if (node.children && node.children.length) {
      const ul = document.createElement("ul");
      node.children.forEach(function (child) {
        ul.appendChild(renderTreeNode(child));
      });
      li.appendChild(ul);
    }
    return li;
  }

  async function showManagedTree(name) {
    if (!managerTree) return;
    managerTree.textContent = "";
    managerTreeTitle.textContent = "目录结构 · " + name;
    const result = await managerCall(
      "GET", "/api/apps/tree?name=" + encodeURIComponent(name)
    );
    if (!result.ok || !result.data) {
      setManagerStatus("未完成：" + managerError(result));
      return;
    }
    const data = result.data;
    managerTree.appendChild(makeNode(
      "div", "manager-meta",
      (data.registered ? "已注册 " + (data.symbol || "") : "未注册") +
      " · " + (data.app_dir || "")
    ));
    if (data.tree) {
      const ul = document.createElement("ul");
      ul.appendChild(renderTreeNode(data.tree));
      managerTree.appendChild(ul);
    }
    if (data.scenarios && data.scenarios.length) {
      managerTree.appendChild(makeNode("div", "manager-meta", "场景"));
      const ul = document.createElement("ul");
      data.scenarios.forEach(function (node) {
        ul.appendChild(renderTreeNode(node));
      });
      managerTree.appendChild(ul);
    }
    if (data.app_c) {
      managerTree.appendChild(makeNode("div", "manager-meta", "注册表"));
      const ul = document.createElement("ul");
      ul.appendChild(renderTreeNode(data.app_c));
      managerTree.appendChild(ul);
    }
    if (data.truncated) {
      managerTree.appendChild(makeNode("div", "manager-meta", "条目较多，已截断。"));
    }
  }

  function addLiveAppOption(name) {
    if (!liveApp || !name) return;
    for (let index = 0; index < liveApp.options.length; index += 1) {
      if (liveApp.options[index].value === name) return;
    }
    liveApp.appendChild(new Option(name, name));
  }

  function removeLiveAppOption(name) {
    if (!liveApp) return;
    for (let index = 0; index < liveApp.options.length; index += 1) {
      if (liveApp.options[index].value === name) {
        liveApp.remove(index);
        break;
      }
    }
    if (lastLiveApp === name) lastLiveApp = liveApp.value || "";
  }

  function previewManagedApp(name) {
    if (!liveApp) {
      setManagerStatus("没有应用下拉，刷新页面后再预览。");
      return;
    }
    addLiveAppOption(name);
    liveApp.value = name;
    lastLiveApp = name;
    closeAppManager();
    previewSelectedApp();
  }

  async function createManagedApp(event) {
    event.preventDefault();
    if (!managerName) return;
    const name = managerName.value.trim();
    if (!/^[a-z][a-z0-9_]{0,31}$/.test(name)) {
      setManagerStatus("应用名需匹配 [a-z][a-z0-9_]{0,31}。");
      return;
    }
    const result = await managerCall("POST", "/api/apps/create", { name: name });
    if (!result.ok || !result.data) {
      setManagerStatus("未完成：" + managerError(result));
      return;
    }
    managerName.value = "";
    addLiveAppOption(name);
    await loadManager();
    setManagerStatus("已创建 " + name + "；需要重新构建后预览。");
  }

  async function deleteManagedApp(name) {
    if (liveRunning || liveStarting) {
      setManagerStatus("测试或录制运行中不能修改应用；停止后再试。");
      return;
    }
    if (!window.confirm("将 \"" + name + "\" 移到 .trash/user/app/？可从回收站恢复。")) {
      return;
    }
    const result = await managerCall("POST", "/api/apps/delete", { name: name });
    if (!result.ok || !result.data) {
      setManagerStatus("未完成：" + managerError(result));
      return;
    }
    removeLiveAppOption(name);
    await loadManager();
    setManagerStatus("已移到回收站：" + (result.data.trash_dir || ".trash/apps"));
  }

  async function restoreTrashedApp(trashId) {
    if (liveRunning || liveStarting) {
      setManagerStatus("测试或录制运行中不能修改应用；停止后再试。");
      return;
    }
    const result = await managerCall(
      "POST", "/api/apps/trash/restore", { trash_id: trashId }
    );
    if (!result.ok || !result.data) {
      setManagerStatus("未完成：" + managerError(result));
      return;
    }
    if (result.data.name) addLiveAppOption(result.data.name);
    await loadManager();
    setManagerStatus("已恢复 " + (result.data.name || "应用") + "。");
  }

  async function purgeTrashedApp(trashId, name) {
    if (liveRunning || liveStarting) {
      setManagerStatus("测试或录制运行中不能修改应用；停止后再试。");
      return;
    }
    if (!window.confirm("永久删除 " + name + "？此操作不可恢复。")) {
      return;
    }
    const result = await managerCall(
      "POST", "/api/apps/trash/delete",
      { trash_id: trashId, confirm: true }
    );
    if (!result.ok || !result.data) {
      setManagerStatus("未完成：" + managerError(result));
      return;
    }
    await loadManager();
    setManagerStatus("已永久删除 " + name + "。");
  }

  function updateManagerAvailability(starting, running) {
    const active = Boolean(starting || running);
    if (managerLiveHint) managerLiveHint.hidden = !active;
    const createButton = $("manager-create");
    if (createButton) createButton.disabled = active;
    const nodes = document.querySelectorAll("#app-manager [data-mutation]");
    for (let index = 0; index < nodes.length; index += 1) {
      const button = nodes[index];
      button.disabled = active || button.dataset.locked === "1";
    }
  }
