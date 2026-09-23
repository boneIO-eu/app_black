// boneIO recovery panel. Plain script on purpose: it has to work when the
// regular frontend bundle, or the API it talks to, is exactly what is broken.
// Everything that came from the device is inserted as text, never as HTML -
// error messages quote config.yaml, and config.yaml is user input.
(function () {
  "use strict";

  // Same key as the regular panel: a session there carries over, and one
  // started here is still valid once the controller is back.
  const TOKEN_KEY = "token";

  const $ = (id) => document.getElementById(id);
  const state = {
    status: null,
    files: [],
    current: null,
    saved: "",
    logs: [],
    jumpLine: null,
  };

  function token() {
    try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
  }
  function setToken(value) {
    try {
      if (value) localStorage.setItem(TOKEN_KEY, value);
      else localStorage.removeItem(TOKEN_KEY);
    } catch (e) { /* private mode: the session lasts as long as the page */ }
    state.memToken = value;
  }

  class ApiError extends Error {
    constructor(status, detail) { super(detail); this.status = status; }
  }

  async function api(method, path, body) {
    const headers = {};
    const t = token() || state.memToken;
    if (t) headers.Authorization = "Bearer " + t;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (res.status === 401) {
      setToken(null);
      showLogin();
      throw new ApiError(401, "Please sign in again.");
    }
    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || res.statusText;
      throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  // ── Views ────────────────────────────────────────────────────────────
  function showLogin() {
    $("login-view").hidden = false;
    $("app-view").hidden = true;
    $("logout").hidden = true;
  }

  async function showApp() {
    $("login-view").hidden = true;
    $("app-view").hidden = false;
    $("logout").hidden = false;
    await loadStatus();
    await loadFiles();
  }

  $("login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    $("login-error").textContent = "";
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const data = await api("POST", "/api/login", {
        username: form.username.value,
        password: form.password.value,
      });
      if (data.role !== "admin") {
        $("login-error").textContent = "Recovery needs an administrator account.";
        return;
      }
      setToken(data.token);
      form.password.value = "";
      await showApp();
    } catch (err) {
      $("login-error").textContent = err.status === 401 ? "Invalid username or password." : err.message;
    } finally {
      button.disabled = false;
    }
  });

  $("logout").addEventListener("click", () => { setToken(null); showLogin(); });

  // ── Status ───────────────────────────────────────────────────────────
  function relativeToConfigDir(file) {
    const dir = state.status && state.status.config_dir;
    if (!file || !dir) return null;
    const prefix = dir.endsWith("/") ? dir : dir + "/";
    return file.startsWith(prefix) ? file.slice(prefix.length) : null;
  }

  function renderWhere(target, reason) {
    target.textContent = "";
    if (!reason.file) return;
    const rel = relativeToConfigDir(reason.file);
    const label = (rel || reason.file) + (reason.line ? ":" + reason.line + (reason.column ? ":" + reason.column : "") : "");
    if (rel && state.files.some((f) => f.path === rel)) {
      const a = document.createElement("a");
      a.href = "#";
      a.textContent = label;
      a.addEventListener("click", (ev) => { ev.preventDefault(); openFile(rel, reason.line); });
      target.append("In ", a);
    } else {
      target.append("In " + label);
    }
  }

  async function loadStatus() {
    let data;
    try {
      data = await api("GET", "/api/recovery/status");
    } catch (err) {
      if (err.status === 403) {
        $("reason-summary").textContent = "This account cannot use recovery; an administrator account is needed.";
      }
      return;
    }
    state.status = data;
    const r = data.reason;
    $("version").textContent = "v" + data.version;
    if (r.kind === "config") {
      $("reason-title").textContent = "The configuration could not be loaded";
      $("reason-summary").textContent =
        "Fix the file below, check it, then restart. Nothing else runs until then.";
    } else {
      $("reason-title").textContent = "boneIO kept crashing while starting";
      $("reason-summary").textContent =
        "It failed " + r.failures + " times in a row, so it stopped trying. " +
        "The error and the log below should say why.";
    }
    renderWhere($("reason-where"), r);
    $("reason-message").textContent = r.message;
    $("reason-details").hidden = !r.details;
    $("reason-traceback").textContent = r.details || "";
    const retry = $("retry-note");
    if (data.retry_in !== null && data.retry_in !== undefined) {
      retry.hidden = false;
      retry.textContent =
        "If nobody uses this panel, boneIO tries a normal start again in about " +
        Math.max(1, Math.round(data.retry_in / 60)) + " min.";
    } else {
      retry.hidden = true;
    }
    if (r.line && !state.jumpLine) state.jumpLine = { file: relativeToConfigDir(r.file), line: r.line };
  }

  // ── Editor ───────────────────────────────────────────────────────────
  const content = $("content");
  const gutter = $("gutter");

  function renderGutter(highlight) {
    const count = content.value.split("\n").length;
    gutter.textContent = "";
    const frag = document.createDocumentFragment();
    for (let i = 1; i <= count; i++) {
      if (i === highlight) {
        const s = document.createElement("span");
        s.className = "hit";
        s.textContent = i + "\n";
        frag.append(s);
      } else {
        frag.append(i + "\n");
      }
    }
    gutter.append(frag);
    gutter.scrollTop = content.scrollTop;
  }

  function markDirty() {
    const dirty = state.current && content.value !== state.saved;
    $("file-state").textContent = dirty ? "Unsaved changes" : "";
    $("save").disabled = !dirty;
  }

  content.addEventListener("input", () => { renderGutter(state.highlight); markDirty(); });
  content.addEventListener("scroll", () => { gutter.scrollTop = content.scrollTop; });
  content.addEventListener("keydown", (ev) => {
    if (ev.key === "Tab") {
      // YAML is indented with spaces; a real tab would break it.
      ev.preventDefault();
      const s = content.selectionStart;
      content.setRangeText("  ", s, content.selectionEnd, "end");
      content.dispatchEvent(new Event("input"));
    } else if ((ev.ctrlKey || ev.metaKey) && ev.key === "s") {
      ev.preventDefault();
      save();
    }
  });

  function goToLine(line) {
    const lines = content.value.split("\n");
    if (!line || line > lines.length) return;
    let start = 0;
    for (let i = 0; i < line - 1; i++) start += lines[i].length + 1;
    content.focus();
    content.setSelectionRange(start, start + lines[line - 1].length);
    const lineHeight = parseFloat(getComputedStyle(content).lineHeight) || 19;
    content.scrollTop = Math.max(0, (line - 5) * lineHeight);
    state.highlight = line;
    renderGutter(line);
  }

  async function loadFiles() {
    try {
      const data = await api("GET", "/api/recovery/files");
      state.files = data.files;
    } catch (err) {
      return;
    }
    const select = $("file-select");
    select.textContent = "";
    for (const f of state.files) {
      const opt = document.createElement("option");
      opt.value = f.path;
      opt.textContent = f.path;
      select.append(opt);
    }
    if (state.status) renderWhere($("reason-where"), state.status.reason);
    const jump = state.jumpLine;
    const first = jump && jump.file && state.files.some((f) => f.path === jump.file) ? jump.file : (state.files[0] || {}).path;
    if (first) await openFile(first, jump && jump.file === first ? jump.line : null);
  }

  async function openFile(path, line) {
    if (state.current && content.value !== state.saved && path !== state.current) {
      if (!confirm("Discard unsaved changes to " + state.current + "?")) {
        $("file-select").value = state.current;
        return;
      }
    }
    selectTab("editor");
    const data = await api("GET", "/api/recovery/file?path=" + encodeURIComponent(path));
    state.current = path;
    state.saved = data.content;
    state.highlight = null;
    content.value = data.content;
    $("file-select").value = path;
    renderGutter(null);
    markDirty();
    if (line) goToLine(line);
  }

  $("file-select").addEventListener("change", (ev) => openFile(ev.target.value));

  async function save() {
    if (!state.current || content.value === state.saved) return;
    $("save").disabled = true;
    try {
      await api("PUT", "/api/recovery/file", { path: state.current, content: content.value });
      state.saved = content.value;
      $("file-state").textContent = "Saved";
    } catch (err) {
      $("file-state").textContent = "Not saved: " + err.message;
      $("save").disabled = false;
    }
  }
  $("save").addEventListener("click", save);

  $("validate").addEventListener("click", async () => {
    if (state.current && content.value !== state.saved) await save();
    const box = $("validation");
    box.hidden = false;
    box.className = "validation busy";
    box.textContent = "Checking the configuration… this takes up to half a minute on a BeagleBone.";
    $("validate").disabled = true;
    try {
      const result = await api("POST", "/api/recovery/validate");
      box.textContent = "";
      if (result.valid) {
        box.className = "validation ok";
        box.textContent = "The configuration loads (" + result.seconds + " s). Restart boneIO to start normally.";
      } else {
        box.className = "validation bad";
        const where = document.createElement("p");
        where.className = "where";
        renderWhere(where, result.error);
        const pre = document.createElement("pre");
        pre.textContent = result.error.message;
        box.append(where, pre);
        const rel = relativeToConfigDir(result.error.file);
        if (rel && rel === state.current && result.error.line) goToLine(result.error.line);
      }
    } catch (err) {
      box.className = "validation bad";
      box.textContent = err.message;
    } finally {
      $("validate").disabled = false;
    }
  });

  // ── Logs ─────────────────────────────────────────────────────────────
  function levelClass(level) {
    const l = String(level).toUpperCase();
    if (["0", "1", "2", "3", "ERROR", "CRITICAL"].includes(l)) return "lvl-err";
    if (["4", "WARNING", "WARN"].includes(l)) return "lvl-warn";
    return "";
  }

  function formatTime(ts) {
    const n = Number(ts);
    if (!Number.isNaN(n) && n > 1e12) return new Date(n / 1000).toLocaleString();
    return ts;
  }

  function renderLogs() {
    const box = $("logs");
    const onlyErrors = $("errors-only").checked;
    box.textContent = "";
    const frag = document.createDocumentFragment();
    for (const e of state.logs) {
      const cls = levelClass(e.level);
      if (onlyErrors && !cls) continue;
      const line = document.createElement("span");
      if (cls) line.className = cls;
      line.textContent = formatTime(e.timestamp) + "  " + e.message + "\n";
      frag.append(line);
    }
    box.append(frag);
    box.scrollTop = box.scrollHeight;
  }

  async function loadLogs() {
    $("logs").textContent = "Loading…";
    try {
      const data = await api("GET", "/api/recovery/logs?limit=500");
      state.logs = data.logs;
      if (!state.logs.length) { $("logs").textContent = "No log entries found."; return; }
      renderLogs();
    } catch (err) {
      $("logs").textContent = err.message;
    }
  }
  $("refresh-logs").addEventListener("click", loadLogs);
  $("errors-only").addEventListener("change", renderLogs);

  // ── Backups ──────────────────────────────────────────────────────────
  function formatSize(bytes) {
    return bytes > 1024 * 1024 ? (bytes / 1024 / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " kB";
  }

  async function loadBackups() {
    const rows = $("backup-rows");
    rows.textContent = "";
    let data;
    try {
      data = await api("GET", "/api/recovery/backups");
    } catch (err) {
      $("backup-note").textContent = err.message;
      return;
    }
    if (!data.backups.length) {
      $("backup-note").textContent = "There are no backups on this controller.";
      return;
    }
    for (const b of data.backups) {
      const tr = document.createElement("tr");
      for (const text of [b.filename, b.modified.replace("T", " "), formatSize(b.size)]) {
        const td = document.createElement("td");
        td.textContent = text;
        tr.append(td);
      }
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.textContent = "Restore";
      btn.addEventListener("click", () => restoreBackup(b.filename, btn));
      td.append(btn);
      tr.append(td);
      rows.append(tr);
    }
  }

  async function restoreBackup(filename, btn) {
    if (!confirm("Restore " + filename + "? The current files are archived first.")) return;
    btn.disabled = true;
    try {
      const r = await api("POST", "/api/recovery/backups/restore", { filename });
      $("backup-note").textContent =
        "Restored " + r.restored.length + " file(s). The previous configuration is in " + r.snapshot +
        ". Check the config, then restart.";
      state.current = null;
      await loadFiles();
      await loadBackups();
    } catch (err) {
      $("backup-note").textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  }

  // ── Tabs ─────────────────────────────────────────────────────────────
  const loaded = {};
  function selectTab(name) {
    for (const b of document.querySelectorAll(".tabs button")) {
      b.setAttribute("aria-selected", String(b.dataset.tab === name));
    }
    for (const t of ["editor", "logs", "backups"]) $("tab-" + t).hidden = t !== name;
    if (!loaded[name]) {
      loaded[name] = true;
      if (name === "logs") loadLogs();
      if (name === "backups") loadBackups();
    }
  }
  for (const b of document.querySelectorAll(".tabs button")) {
    b.addEventListener("click", () => selectTab(b.dataset.tab));
  }

  // ── Restart ──────────────────────────────────────────────────────────
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitForController() {
    const note = $("restart-note");
    const started = Date.now();
    await sleep(4000);
    while (Date.now() - started < 5 * 60 * 1000) {
      try {
        const res = await fetch("/api/auth/required", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (!data.recovery) { location.href = "/"; return; }
          // Recovery again: it did not start. The page shows why.
          location.reload();
          return;
        }
      } catch (e) { /* not listening yet */ }
      note.textContent = "Waiting for boneIO to come back… " + Math.round((Date.now() - started) / 1000) + " s";
      await sleep(2000);
    }
    note.textContent = "boneIO has not come back after five minutes. Check the display, or the log over SSH.";
  }

  $("restart").addEventListener("click", async () => {
    if (state.current && content.value !== state.saved &&
        !confirm("You have unsaved changes to " + state.current + ". Restart anyway?")) return;
    $("restart").disabled = true;
    $("restart-note").textContent = "Restarting…";
    try {
      await api("POST", "/api/recovery/restart");
    } catch (err) {
      $("restart-note").textContent = err.message;
      $("restart").disabled = false;
      return;
    }
    waitForController();
  });

  window.addEventListener("beforeunload", (ev) => {
    if (state.current && content.value !== state.saved && !$("restart").disabled) {
      ev.preventDefault();
      ev.returnValue = "";
    }
  });

  // ── Start ────────────────────────────────────────────────────────────
  $("save").disabled = true;
  if (token()) showApp().catch(() => showLogin());
  else showLogin();
})();
