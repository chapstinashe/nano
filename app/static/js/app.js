/**
 * Nano RAG — Main application
 */
(function () {
  "use strict";

  const ALLOWED_EXT = ["pdf", "docx", "txt", "csv", "xlsx"];
  const MAX_TOP_K = 8;
  const MOBILE_BREAKPOINT = 768;

  const state = {
    chats: [],
    activeChatId: null,
    settings: { theme: "dark" },
    pendingFiles: [],
    documentIds: [],
    authUser: null,
    guestSessionId: null,
    guestUploadLimit: 1,
    isSending: false,
    sidebarOpen: false,
  };

  // ===== DOM refs =====
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const els = {
    app: $("#app"),
    sidebar: $("#sidebar"),
    sidebarBackdrop: $("#sidebarBackdrop"),
    hamburgerBtn: $("#hamburgerBtn"),
    sidebarPanelBtn: $("#sidebarPanelBtn"),
    sidebarClose: $("#sidebarClose"),
    chatHistoryList: $("#chatHistoryList"),
    welcome: $("#welcome"),
    messages: $("#messages"),
    chatForm: $("#chatForm"),
    chatInput: $("#chatInput"),
    sendBtn: $("#sendBtn"),
    themeToggle: $("#themeToggle"),
    themeSelect: $("#themeSelect"),
    toast: $("#toast"),
    fileList: $("#fileList"),
    dropzone: $("#dropzone"),
    fileInput: $("#fileInput"),
    uploadAllBtn: $("#uploadAllBtn"),
    authStatus: $("#authStatus"),
    loginBtn: $("#loginBtn"),
    registerBtn: $("#registerBtn"),
    logoutBtn: $("#logoutBtn"),
  };

  function isMobile() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  function initMobileViewport() {
    const root = document.documentElement;
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);

    function syncLayoutHeight() {
      if (!mq.matches) {
        root.style.removeProperty("--layout-height");
        return;
      }
      const vv = window.visualViewport;
      if (vv) {
        root.style.setProperty("--layout-height", `${Math.round(vv.height)}px`);
      } else {
        root.style.removeProperty("--layout-height");
      }
    }

    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncLayoutHeight);
      window.visualViewport.addEventListener("scroll", syncLayoutHeight);
    }
    window.addEventListener("resize", syncLayoutHeight);
    mq.addEventListener("change", syncLayoutHeight);
    syncLayoutHeight();
  }

  function openSidebar() {
    state.sidebarOpen = true;
    els.sidebar.classList.add("open");
    els.app.classList.remove("sidebar-collapsed");
    if (isMobile()) {
      els.sidebarBackdrop.classList.remove("hidden");
      requestAnimationFrame(() => els.sidebarBackdrop.classList.add("visible"));
    }
  }

  function closeSidebar() {
    state.sidebarOpen = false;
    els.sidebar.classList.remove("open");
    els.sidebarBackdrop.classList.remove("visible");
    setTimeout(() => {
      if (!state.sidebarOpen) els.sidebarBackdrop.classList.add("hidden");
    }, 300);
    if (!isMobile()) {
      els.app.classList.add("sidebar-collapsed");
    }
  }

  function isSidebarVisible() {
    return isMobile()
      ? els.sidebar.classList.contains("open")
      : !els.app.classList.contains("sidebar-collapsed");
  }

  function toggleSidebar() {
    if (isSidebarVisible()) {
      closeSidebar();
    } else {
      openSidebar();
    }
  }

  function initSidebarLayout() {
    if (isMobile()) {
      els.sidebar.classList.remove("open");
      els.app.classList.remove("sidebar-collapsed");
      els.sidebarBackdrop.classList.remove("visible");
      els.sidebarBackdrop.classList.add("hidden");
      state.sidebarOpen = false;
    } else {
      els.sidebar.classList.add("open");
      els.app.classList.remove("sidebar-collapsed");
      els.sidebarBackdrop.classList.remove("visible");
      els.sidebarBackdrop.classList.add("hidden");
      state.sidebarOpen = true;
    }
  }

  // ===== Storage =====
  function isAuthenticated() {
    return Boolean(state.authUser?.id);
  }

  function mapRemoteChat(chat) {
    return {
      id: chat.id,
      title: chat.title || "New chat",
      messages: chat.messages || [],
      createdAt: chat.created_at || chat.createdAt || Date.now(),
    };
  }

  function mapLocalChat(chat) {
    return {
      id: chat.id,
      title: chat.title || "New chat",
      messages: chat.messages || [],
      createdAt: chat.createdAt || Date.now(),
    };
  }

  function setActiveChatId(chatId) {
    state.activeChatId = chatId || null;
    if (isAuthenticated()) {
      persistPreferences();
    } else {
      saveChats();
    }
  }

  function loadState() {
    state.settings = { theme: "dark" };
    state.chats = [];
    state.activeChatId = null;
    state.documentIds = [];
    state.guestSessionId = null;
  }

  let preferencesTimer = null;
  function persistPreferences() {
    clearTimeout(preferencesTimer);
    preferencesTimer = setTimeout(async () => {
      try {
        const payload = { theme: state.settings.theme };
        if (isAuthenticated()) {
          payload.active_chat_id = state.activeChatId || "";
        }
        await API.savePreferences(payload);
      } catch (_) {
        /* UI still works if preferences sync fails briefly */
      }
    }, 300);
  }

  async function loadPreferencesFromServer() {
    try {
      const prefs = await API.getPreferences();
      state.settings.theme = prefs.theme || "dark";
      if (isAuthenticated() && prefs.active_chat_id) {
        state.activeChatId = prefs.active_chat_id;
      }
      applyTheme(state.settings.theme);
    } catch {
      state.settings.theme = "dark";
      applyTheme("dark");
    }
  }

  async function loadGuestChatsFromStorage() {
    if (!state.guestSessionId) {
      state.chats = [];
      state.activeChatId = null;
      return;
    }

    const stored = await GuestStorage.load(state.guestSessionId);
    state.chats = (stored.chats || []).map(mapLocalChat);
    if (stored.activeChatId && state.chats.some((chat) => chat.id === stored.activeChatId)) {
      state.activeChatId = stored.activeChatId;
      return;
    }
    state.activeChatId = state.chats[0]?.id || null;
  }

  async function syncChatsFromServer() {
    if (!isAuthenticated()) {
      return;
    }
    await loadPreferencesFromServer();
    const remote = await API.listChats();
    state.chats = (remote.chats || []).map(mapRemoteChat);
    if (state.activeChatId && state.chats.some((c) => c.id === state.activeChatId)) {
      return;
    }
    setActiveChatId(state.chats[0]?.id || null);
  }

  function saveChats() {
    if (isAuthenticated()) {
      setActiveChatId(state.activeChatId);
      Promise.all(state.chats.map((chat) => API.saveChat(chat))).catch(() => {
        // Keep local UI state if Cosmos sync fails temporarily.
      });
      return;
    }

    if (!state.guestSessionId) {
      return;
    }

    GuestStorage.save(state.guestSessionId, {
      chats: state.chats,
      activeChatId: state.activeChatId,
    }).catch(() => {
      // Keep local UI state if browser storage fails briefly.
    });
  }

  async function refreshDocumentIdsFromServer() {
    if (!isAuthenticated()) {
      if (!state.guestSessionId) {
        state.documentIds = [];
        return;
      }
      state.documentIds = await GuestDocuments.listDocumentIds(state.guestSessionId);
      return;
    }
    try {
      const data = await API.listDocuments();
      state.documentIds = (data.documents || []).map((doc) => doc.document_id).filter(Boolean);
    } catch {
      state.documentIds = [];
    }
  }

  async function bootstrapGuest() {
    await API.syncSession();
    const session = await API.ensureSession();
    state.guestSessionId = session.session_id || "";
    state.guestUploadLimit = Number(session.guest_upload_limit) || 1;
    GuestStorage.clearLegacy();
    await loadGuestChatsFromStorage();
    await loadPreferencesFromServer();
    await refreshDocumentIdsFromServer();
    renderChatHistory();
    renderMessages();
  }

  function getActiveChat() {
    return state.chats.find((c) => c.id === state.activeChatId) || null;
  }

  function createChat(title) {
    const chat = {
      id: crypto.randomUUID(),
      title: title || "New chat",
      messages: [],
      createdAt: Date.now(),
    };
    state.chats.unshift(chat);
    setActiveChatId(chat.id);
    saveChats();
    return chat;
  }

  // ===== Theme =====
  function getSystemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    const resolved = theme === "system" ? getSystemTheme() : theme;
    document.documentElement.setAttribute("data-theme", resolved);
    if (els.themeSelect) els.themeSelect.value = theme;
  }

  function initTheme() {
    applyTheme(state.settings.theme || "dark");
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (state.settings.theme === "system") applyTheme("system");
    });
  }

  function cycleTheme() {
    const order = ["dark", "light", "system"];
    const idx = order.indexOf(state.settings.theme);
    state.settings.theme = order[(idx + 1) % order.length];
    applyTheme(state.settings.theme);
    persistPreferences();
    showToast(`Theme: ${state.settings.theme}`);
  }

  // ===== Toast =====
  let toastTimer;
  function showToast(msg, duration = 3000) {
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.add("hidden"), duration);
  }

  // ===== Modals =====
  function openModal(id) {
    const overlay = document.getElementById(id);
    if (overlay) overlay.classList.remove("hidden");
  }

  function closeModal(id) {
    const overlay = document.getElementById(id);
    if (overlay) overlay.classList.add("hidden");
  }

  function closeAllModals() {
    $$(".modal-overlay").forEach((m) => m.classList.add("hidden"));
    $("#brandMenu")?.classList.add("hidden");
  }

  function renderAuthState() {
    const user = state.authUser;
    if (user?.email) {
      els.authStatus.textContent = user.email;
      els.loginBtn.classList.add("hidden");
      els.registerBtn.classList.add("hidden");
      els.logoutBtn.classList.remove("hidden");
      return;
    }
    els.authStatus.textContent = "Guest";
    els.loginBtn.classList.remove("hidden");
    els.registerBtn.classList.remove("hidden");
    els.logoutBtn.classList.add("hidden");
  }

  async function bootstrapAuth() {
    try {
      const data = await API.me();
      state.authUser = data.user || null;
      if (state.authUser?.id) {
        GuestStorage.clear();
        await GuestDocuments.clearAll();
        state.guestSessionId = null;
        try {
          await syncChatsFromServer();
          saveChats();
          await refreshDocumentIdsFromServer();
          renderChatHistory();
          renderMessages();
        } catch {
          // Stay authenticated even if Cosmos sync fails temporarily.
        }
      }
    } catch {
      state.authUser = null;
      try {
        await bootstrapGuest();
      } catch (err) {
        console.warn("Guest bootstrap failed:", err.message || err);
        renderChatHistory();
        renderMessages();
      }
    }
    renderAuthState();
  }

  // ===== Sidebar =====
  function renderChatHistory() {
    els.chatHistoryList.innerHTML = "";
    state.chats.forEach((chat) => {
      const row = document.createElement("div");
      row.className = "chat-history-row" + (chat.id === state.activeChatId ? " active" : "");

      const btn = document.createElement("button");
      btn.className = "chat-history-item";
      btn.type = "button";
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span>${escapeHtml(chat.title)}</span>`;
      btn.addEventListener("click", () => loadChat(chat.id));

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "chat-history-delete";
      deleteBtn.type = "button";
      deleteBtn.setAttribute("aria-label", "Delete chat");
      deleteBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`;
      deleteBtn.addEventListener("click", (e) => deleteChat(chat.id, e));

      row.appendChild(btn);
      row.appendChild(deleteBtn);
      els.chatHistoryList.appendChild(row);
    });
  }

  function deleteChat(id, e) {
    e.stopPropagation();
    const chat = state.chats.find((c) => c.id === id);
    if (!chat) return;

    state.chats = state.chats.filter((c) => c.id !== id);

    if (state.activeChatId === id) {
      setActiveChatId(state.chats[0]?.id || null);
    }

    saveChats();
    if (isAuthenticated()) {
      API.deleteChat(id).catch(() => {
        // Keep local state even if remote deletion fails.
      });
    }
    renderChatHistory();
    renderMessages();
    showToast("Chat deleted");
  }

  function loadChat(id) {
    setActiveChatId(id);
    renderChatHistory();
    renderMessages();
    closeAllModals();
    if (isMobile()) closeSidebar();
  }

  function newChat() {
    createChat("New chat");
    renderChatHistory();
    renderMessages();
    els.chatInput.focus();
    showToast("New chat started");
  }

  // ===== Messages =====
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  const CHECK_ICON_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

  function showCopySuccess(button) {
    if (button.dataset.copyTimer) {
      clearTimeout(Number(button.dataset.copyTimer));
    }
    if (!button.dataset.copyIcon) {
      button.dataset.copyIcon = button.innerHTML;
      button.dataset.copyLabel = button.getAttribute("aria-label") || "Copy";
      button.dataset.copyTitle = button.getAttribute("title") || "Copy";
    }
    button.classList.add("is-copied");
    button.innerHTML = CHECK_ICON_SVG;
    button.setAttribute("aria-label", "Copied");
    button.setAttribute("title", "Copied");
    button.dataset.copyTimer = String(
      setTimeout(() => {
        button.innerHTML = button.dataset.copyIcon;
        button.classList.remove("is-copied");
        button.setAttribute("aria-label", button.dataset.copyLabel);
        button.setAttribute("title", button.dataset.copyTitle);
        delete button.dataset.copyTimer;
      }, 2000)
    );
  }

  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(text || "");
      if (button) {
        showCopySuccess(button);
      } else {
        showToast("Copied");
      }
    } catch {
      showToast("Copy failed");
    }
  }

  async function shareText(text) {
    const payload = { text: text || "" };
    try {
      if (navigator.share) {
        await navigator.share(payload);
        return;
      }
      await navigator.clipboard.writeText(text || "");
      showToast("Share not available. Copied instead");
    } catch {
      showToast("Share failed");
    }
  }

  function bindMessageActions(container) {
    container.querySelectorAll(".message-copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => copyText(btn.dataset.messageText || "", btn));
    });

    container.querySelectorAll(".message-share-btn").forEach((btn) => {
      btn.addEventListener("click", () => shareText(btn.dataset.messageText || ""));
    });
  }

  function renderMessages() {
    const chat = getActiveChat();
    if (!chat || chat.messages.length === 0) {
      els.welcome.classList.remove("hidden");
      els.messages.classList.add("hidden");
      els.messages.innerHTML = "";
      return;
    }

    els.welcome.classList.add("hidden");
    els.messages.classList.remove("hidden");
    els.messages.innerHTML = "";

    chat.messages.forEach((msg) => {
      els.messages.appendChild(buildMessageEl(msg));
    });

    scrollToBottom();
  }

  function formatAnswerHtml(content, sources) {
    const safe = escapeHtml(content);
    if (!sources?.length) return safe;

    return safe.replace(/\[(\d+)\]/g, (match, num) => {
      const hasRef = sources.some((src) => String(src.ref ?? src.source_ref) === num);
      if (!hasRef) return match;
      return `<button type="button" class="inline-citation" data-ref="${num}">${match}</button>`;
    });
  }

  function showSourcePanel(container, ref) {
    const panel = container.querySelector(".message-sources");
    if (!panel) return;

    const refKey = String(ref);
    const target = panel.querySelector(`.citation-item[data-ref="${refKey}"]`);
    if (!target) return;

    const detail = panel.querySelector(".message-sources-detail");
    const isOpen = panel.classList.contains("is-open");
    const isSame = target.classList.contains("is-open");

    if (isOpen && isSame) {
      panel.classList.remove("is-open");
      if (detail) detail.classList.remove("is-open");
      panel.querySelectorAll(".citation-item").forEach((item) => item.classList.remove("is-open"));
      container.querySelectorAll(".inline-citation, .citation-ref-btn").forEach((btn) => {
        btn.classList.remove("active");
      });
      return;
    }

    panel.classList.add("is-open");
    if (detail) detail.classList.add("is-open");
    panel.querySelectorAll(".citation-item").forEach((item) => item.classList.remove("is-open", "citation-item-highlight"));
    target.classList.add("is-open", "citation-item-highlight");

    const title = panel.querySelector(".message-sources-title");
    if (title) title.textContent = `Source [${refKey}]`;

    container.querySelectorAll(".inline-citation, .citation-ref-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.ref === refKey);
    });

    target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setTimeout(() => target.classList.remove("citation-item-highlight"), 1600);

    renderDocumentForCitation(container, target).catch((err) => {
      if (target.querySelector(".citation-view")) {
        showToast(err.message || "Failed to load source document");
      }
    });
  }

  async function loadDocumentText(documentId) {
    if (isAuthenticated()) {
      return API.documentText(documentId, 0, 0, true);
    }
    if (!state.guestSessionId) {
      throw new Error("Document not found");
    }
    const data = await GuestDocuments.getText(state.guestSessionId, documentId);
    if (!data?.text) {
      throw new Error("Document not found");
    }
    return data;
  }

  async function renderDocumentForCitation(container, citationItem) {
    const panel = container.querySelector(".message-sources");
    if (!panel || !citationItem) return;

    const citationBtn = citationItem.querySelector(".citation-view");
    const documentId = citationBtn?.dataset.documentId || citationItem.dataset.documentId;
    const clickedRef = citationItem.dataset.ref || citationBtn?.dataset.ref || "";
    const filename = citationBtn?.dataset.filename || citationItem.dataset.document || "Document";
    if (!documentId) return;

    const data = await loadDocumentText(documentId);
    const text = data.text || "";
    const { compact, map } = buildCompactMap(text);

    // Locate each cited chunk by its actual text content. Stored character
    // offsets drift (chunk overlap + whitespace normalization), so we anchor
    // the chunk in the document by matching its compacted (whitespace-free)
    // text. This guarantees the highlight matches the chunk that was used.
    const spans = [];
    Array.from(panel.querySelectorAll(`.citation-item[data-document-id="${documentId}"]`)).forEach((item) => {
      const ref = String(item.dataset.ref || "");
      const region =
        locateCompactRegion(item.dataset.paragraph || "", compact, map) ||
        locateCompactRegion(item.dataset.excerpt || "", compact, map) ||
        storedOffsetRegion(item, text.length);
      if (region) spans.push({ ...region, ref });
    });
    spans.sort((a, b) => a.start - b.start);

    if (!spans.length) {
      throw new Error("No highlight spans found for this source");
    }

    const merged = [];
    for (const span of spans) {
      const last = merged[merged.length - 1];
      if (!last || span.start > last.end) {
        merged.push({ start: span.start, end: span.end, refs: [span.ref] });
      } else {
        last.end = Math.max(last.end, span.end);
        if (!last.refs.includes(span.ref)) last.refs.push(span.ref);
      }
    }

    let cursor = 0;
    let html = "";
    merged.forEach((span, idx) => {
      const safeStart = clamp(span.start, 0, text.length);
      const safeEnd = clamp(span.end, safeStart, text.length);
      html += escapeHtml(text.slice(cursor, safeStart));
      html += `<mark class="doc-highlight" data-mark-refs="${escapeHtml(span.refs.join(","))}" data-mark-index="${idx}">${escapeHtml(text.slice(safeStart, safeEnd) || " ")}</mark>`;
      cursor = safeEnd;
    });
    html += escapeHtml(text.slice(cursor));

    const viewer = panel.querySelector(".source-document-view");
    const pre = panel.querySelector(".source-doc-inline");
    const meta = panel.querySelector(".source-doc-inline-meta");
    if (!viewer || !pre || !meta) return;

    pre.innerHTML = html;
    meta.textContent = `${data.filename || filename} · ${merged.length} highlighted passage${merged.length === 1 ? "" : "s"}`;
    viewer.classList.remove("hidden");

    requestAnimationFrame(() => {
      pre.querySelectorAll(".doc-highlight").forEach((mark) => {
        mark.classList.remove("doc-highlight-active");
      });
      const target = Array.from(pre.querySelectorAll(".doc-highlight")).find((mark) => {
        const refs = (mark.dataset.markRefs || "").split(",");
        return refs.includes(String(clickedRef));
      }) || pre.querySelector(".doc-highlight");
      if (target) {
        target.classList.add("doc-highlight-active");
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        const viewer = panel.querySelector(".source-document-view");
        if (viewer) viewer.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });
  }

  function bindCitationLinks(container) {
    const openRef = (ref) => showSourcePanel(container, ref);

    container.querySelectorAll(".inline-citation").forEach((btn) => {
      btn.addEventListener("click", () => openRef(btn.dataset.ref));
    });

    container.querySelectorAll(".citation-ref-btn").forEach((btn) => {
      btn.addEventListener("click", () => openRef(btn.dataset.ref));
    });

    container.querySelector(".source-panel-close")?.addEventListener("click", () => {
      const panel = container.querySelector(".message-sources");
      if (!panel) return;
      panel.classList.remove("is-open");
      panel.querySelector(".message-sources-detail")?.classList.remove("is-open");
      panel.querySelectorAll(".citation-item").forEach((item) => item.classList.remove("is-open"));
      container.querySelectorAll(".inline-citation, .citation-ref-btn").forEach((btn) => {
        btn.classList.remove("active");
      });
      panel.querySelector(".source-document-view")?.classList.add("hidden");
    });

    container.querySelectorAll(".citation-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = btn.closest(".citation-item");
        const expanded = item.classList.toggle("expanded");
        btn.textContent = expanded ? "Show less" : "Show full chunk";
      });
    });

    container.querySelectorAll(".citation-download-local").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const blob = await GuestDocuments.downloadBlob(state.guestSessionId, btn.dataset.documentId);
          if (!blob) {
            showToast("File not found locally");
            return;
          }
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = btn.dataset.filename || "document";
          link.click();
          URL.revokeObjectURL(url);
        } catch (err) {
          showToast(err.message || "Download failed");
        }
      });
    });

    container.querySelectorAll(".citation-view").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const item = btn.closest(".citation-item");
          await renderDocumentForCitation(container, item);
        } catch (err) {
          showToast(err.message || "Failed to load source document");
        }
      });
    });

    container.querySelector(".source-doc-inline-close")?.addEventListener("click", () => {
      const viewer = container.querySelector(".source-document-view");
      if (viewer) viewer.classList.add("hidden");
    });
  }

  function formatSourceDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch {
      return "";
    }
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function compactify(text) {
    return (text || "").replace(/\s+/g, "");
  }

  // Build a whitespace-free copy of the raw document plus a map from each
  // compact-index back to the original raw-character index.
  function buildCompactMap(raw) {
    const map = [];
    let compact = "";
    for (let i = 0; i < raw.length; i++) {
      if (/\s/.test(raw[i])) continue;
      compact += raw[i];
      map.push(i);
    }
    return { compact, map };
  }

  // Locate a chunk's region inside the document by matching its compacted text.
  // Falls back to windowed anchors so chunks that carry a duplicated overlap
  // prefix (and therefore never appear verbatim) are still located by their
  // findable fragments. Returns raw {start, end} or null.
  function locateCompactRegion(needleRaw, compact, map, win = 48, step = 40, minAnchor = 24) {
    const needle = compactify(needleRaw);
    if (!needle || !map.length) return null;

    const whole = compact.indexOf(needle);
    if (whole >= 0) {
      return { start: map[whole], end: map[whole + needle.length - 1] + 1 };
    }

    const starts = [];
    const ends = [];
    const n = needle.length;
    for (let i = 0; i < n; i += step) {
      let frag = needle.slice(i, i + win);
      if (frag.length < minAnchor) {
        frag = needle.slice(Math.max(0, n - win));
        if (frag.length < minAnchor) break;
      }
      const pos = compact.indexOf(frag);
      if (pos >= 0) {
        starts.push(map[pos]);
        ends.push(map[pos + frag.length - 1] + 1);
      }
    }
    if (!starts.length) return null;
    return { start: Math.min(...starts), end: Math.max(...ends) };
  }

  function storedOffsetRegion(item, rawLength) {
    const btn = item.querySelector(".citation-view");
    const start = Number(btn?.dataset.start ?? -1);
    const end = Number(btn?.dataset.end ?? -1);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) {
      return null;
    }
    return { start: clamp(start, 0, rawLength), end: clamp(end, start, rawLength) };
  }

  function buildChunkMetaHtml(src) {
    const primary = [];
    if (src.word_count != null) primary.push(`${src.word_count} words`);
    if (src.source_type) primary.push(src.source_type.toUpperCase());

    const secondary = [];
    const indexed = formatSourceDate(src.indexed_at);
    if (indexed) secondary.push(`Indexed ${indexed}`);

    const primaryHtml = primary.length
      ? `<div class="citation-meta citation-meta-primary">${primary.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
      : "";
    const secondaryHtml = secondary.length
      ? `<div class="citation-meta citation-meta-secondary">${secondary.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
      : "";

    return primaryHtml + secondaryHtml;
  }

  function buildSourcesHtml(sources) {
    if (!sources?.length) return "";

    const refButtons = sources
      .map((src) => {
        const refKey = String(src.ref ?? src.source_ref ?? "");
        return `<button type="button" class="citation-ref-btn" data-ref="${escapeHtml(refKey)}" title="View source ${refKey} in document">[${src.ref}]</button>`;
      })
      .join("");

    const items = sources
      .map((src) => {
        const refKey = String(src.ref ?? src.source_ref ?? "");
        const excerpt = src.excerpt || src.paragraph || "";
        const fullText = src.paragraph || excerpt;
        const section = src.section || src.chunk_position || "";

        const downloadBtn =
          src.document_id && src.source !== "database"
            ? isAuthenticated()
              ? `<a class="citation-download" href="${API.documentDownloadUrl(src.document_id)}" title="Download document">Download document</a>`
              : `<button type="button" class="citation-download citation-download-local" data-document-id="${escapeHtml(src.document_id)}" data-filename="${escapeHtml(src.document)}" title="Download document">Download document</button>`
            : "";

        const canView = src.document_id && src.source !== "database" && src.chunk_start != null && src.chunk_end != null;
        const viewBtn = canView
          ? `<button type="button" class="citation-view" data-document-id="${escapeHtml(src.document_id)}" data-start="${Number(src.chunk_start)}" data-end="${Number(src.chunk_end)}" data-filename="${escapeHtml(src.document)}" data-ref="${escapeHtml(refKey)}" title="View highlighted passage in document">View in document</button>`
          : "";

        const chunkMeta = buildChunkMetaHtml(src);
        const excerptHtml = excerpt
          ? `<p class="citation-excerpt">${escapeHtml(excerpt)}</p>`
          : "";

        return `
          <li class="citation-item"
              data-ref="${refKey}"
              data-document-id="${escapeHtml(src.document_id || "")}"
              data-document="${escapeHtml(src.document || "")}"
              data-paragraph="${escapeHtml(fullText || "")}"
              data-excerpt="${escapeHtml(excerpt || "")}"
              id="citation-${refKey}">
            <div class="citation-header">
              <button type="button" class="citation-ref citation-ref-btn" data-ref="${escapeHtml(refKey)}" title="Jump to highlighted section">[${src.ref}]</button>
              <span class="citation-doc" title="${escapeHtml(src.document)}">${escapeHtml(src.document)}</span>
              ${section ? `<span class="citation-section">${escapeHtml(section)}</span>` : ""}
              ${downloadBtn}
              ${viewBtn}
            </div>
            ${chunkMeta}
            ${excerptHtml}
          </li>
        `;
      })
      .join("");

    return `
      <div class="message-sources">
        <div class="message-source-refs" aria-label="Reference list">
          <span class="message-source-refs-label">Sources</span>
          <div class="message-source-refs-list">${refButtons}</div>
        </div>
        <div class="message-sources-detail">
          <div class="message-sources-header">
            <div class="message-sources-title">Source</div>
            <button type="button" class="source-panel-close" aria-label="Close source">✕</button>
          </div>
          <ol class="citation-list">${items}</ol>
          <div class="source-document-view hidden">
            <div class="source-document-view-header">
              <div class="source-doc-inline-meta"></div>
              <button type="button" class="source-doc-inline-close" aria-label="Close document view">✕</button>
            </div>
            <pre class="source-doc source-doc-inline"></pre>
          </div>
        </div>
      </div>
    `;
  }

  function buildMessageEl(msg) {
    const role = msg.role;
    const content = msg.content;
    const div = document.createElement("div");
    div.className = `message ${role}`;
    const avatar = role === "user" ? "U" : "n";
    const sourcesHtml =
      role === "assistant" && msg.sources?.length ? buildSourcesHtml(msg.sources) : "";
    const contentHtml =
      role === "assistant" ? formatAnswerHtml(content, msg.sources) : escapeHtml(content);
    const userHoverCopy =
      role === "user"
        ? `<button type="button" class="message-action-btn message-copy-btn user-hover-copy icon-only" data-message-text="${escapeHtml(content)}" aria-label="Copy question" title="Copy question"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>`
        : "";
    const assistantActions =
      role === "assistant"
        ? `<div class="message-actions"><button type="button" class="message-action-btn message-copy-btn icon-only" data-message-text="${escapeHtml(content)}" aria-label="Copy answer" title="Copy answer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button><button type="button" class="message-action-btn message-share-btn icon-only" data-message-text="${escapeHtml(content)}" aria-label="Share answer" title="Share answer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></button></div>`
        : "";
    div.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-body">
        ${userHoverCopy}
        <div class="message-content">${contentHtml}</div>
        ${assistantActions}
        ${sourcesHtml}
      </div>
    `;
    if (role === "assistant") bindCitationLinks(div);
    bindMessageActions(div);
    return div;
  }

  function scrollToBottom() {
    const area = $("#chatArea");
    area.scrollTop = area.scrollHeight;
  }

  async function sendMessage() {
    const text = els.chatInput.value.trim();
    if (!text || state.isSending) return;

    let chat = getActiveChat();
    if (!chat) chat = createChat(text.slice(0, 40));

    if (chat.messages.length === 0) {
      chat.title = text.slice(0, 40) + (text.length > 40 ? "…" : "");
      renderChatHistory();
    }

    chat.messages.push({ role: "user", content: text });
    saveChats();

    els.chatInput.value = "";
    autoResizeInput();
    updateSendBtn();
    renderMessages();

    state.isSending = true;
    els.sendBtn.disabled = true;

    const loadingEl = document.createElement("div");
    loadingEl.className = "message assistant loading";
    loadingEl.innerHTML = `<div class="message-avatar">n</div><div class="message-body"><div class="message-content"></div></div>`;
    els.messages.appendChild(loadingEl);
    scrollToBottom();

    const contentEl = loadingEl.querySelector(".message-content");
    const bodyEl = loadingEl.querySelector(".message-body");
    let answer = "";
    let sources = [];
    let contextChunks = null;

    try {
      if (!isAuthenticated()) {
        if (!state.documentIds.length) {
          throw new Error("Upload a file before chatting.");
        }
        const queryEmbedding = await API.embedQuery(text);
        const retrieved = await GuestDocuments.search(
          state.guestSessionId,
          text,
          queryEmbedding,
          MAX_TOP_K,
          state.documentIds
        );
        if (!retrieved.length) {
          throw new Error("No relevant content found in your uploaded files.");
        }
        contextChunks = retrieved.map((chunk) => ({
          id: chunk.id,
          text: chunk.text,
          score: chunk.score,
          metadata: chunk.metadata,
        }));
      }

      const result = await API.chatStream(
        text,
        MAX_TOP_K,
        (_token, full) => {
          contentEl.innerHTML = formatAnswerHtml(full, sources);
          loadingEl.classList.remove("loading");
          scrollToBottom();
        },
        (s) => {
          sources = s;
          const existing = bodyEl.querySelector(".message-sources");
          if (existing) existing.remove();
          bodyEl.insertAdjacentHTML("beforeend", buildSourcesHtml(s));
          contentEl.innerHTML = formatAnswerHtml(contentEl.textContent || answer, sources);
          bindCitationLinks(loadingEl);
          scrollToBottom();
        },
        state.documentIds,
        contextChunks
      );
      answer = result.text;
      sources = result.sources || sources;
    } catch (err) {
      answer = `Sorry, something went wrong: ${err.message}`;
      contentEl.textContent = answer;
      loadingEl.classList.remove("loading");
    }

    loadingEl.remove();
    chat.messages.push({ role: "assistant", content: answer, sources });
    saveChats();
    renderMessages();

    state.isSending = false;
    updateSendBtn();
  }

  // ===== Input =====
  function autoResizeInput() {
    const ta = els.chatInput;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }

  function updateSendBtn() {
    els.sendBtn.disabled = !els.chatInput.value.trim() || state.isSending;
  }

  // ===== Upload =====
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function fileIcon(name) {
    const ext = name.split(".").pop()?.toLowerCase();
    const icons = { pdf: "📕", docx: "📘", txt: "📄", csv: "📊", xlsx: "📊" };
    return icons[ext] || "📎";
  }

  function validateFile(file) {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      return `Unsupported type: .${ext}`;
    }
    return null;
  }

  function addFiles(fileList) {
    Array.from(fileList).forEach((file) => {
      const err = validateFile(file);
      if (err) {
        showToast(err);
        return;
      }
      if (state.pendingFiles.some((f) => f.file.name === file.name && f.file.size === file.size)) return;
      state.pendingFiles.push({
        id: crypto.randomUUID(),
        file,
        status: "pending",
        progress: 0,
        error: null,
      });
    });
    renderFileList();
  }

  function renderFileList() {
    els.fileList.innerHTML = "";
    state.pendingFiles.forEach((item) => {
      const li = document.createElement("li");
      li.className = `file-item${item.status === "error" ? " has-error" : ""}`;
      const errorHtml =
        item.status === "error" && item.error
          ? `<div class="file-item-error">${escapeHtml(item.error)}</div>`
          : "";
      li.innerHTML = `
        <div class="file-item-icon">${fileIcon(item.file.name)}</div>
        <div class="file-item-info">
          <div class="file-item-name">${escapeHtml(item.file.name)}</div>
          <div class="file-item-meta">${formatSize(item.file.size)}</div>
          ${errorHtml}
          ${item.status === "uploading"
            ? `<div class="progress-bar"><div class="progress-fill" style="width:${item.progress}%"></div></div>`
            : ""}
          ${item.status === "indexing"
            ? `<div class="progress-bar indexing"><div class="progress-fill"></div></div>`
            : ""}
        </div>
        <span class="file-item-status ${item.status}">${statusLabel(item)}</span>
        ${item.status === "pending" ? `<button class="file-item-remove" data-id="${item.id}" type="button" aria-label="Remove">✕</button>` : ""}
      `;
      els.fileList.appendChild(li);
    });

    els.uploadAllBtn.disabled = !state.pendingFiles.some((f) => f.status === "pending");

    els.fileList.querySelectorAll(".file-item-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.pendingFiles = state.pendingFiles.filter((f) => f.id !== btn.dataset.id);
        renderFileList();
      });
    });
  }

  function statusLabel(item) {
    switch (item.status) {
      case "pending": return "Ready";
      case "uploading": return `${item.progress}%`;
      case "indexing": return "Indexing...";
      case "done": return "Indexed ✓";
      case "error": return "Failed";
      default: return "";
    }
  }

  async function uploadAll() {
    const pending = state.pendingFiles.filter((f) => f.status === "pending");
    if (!pending.length) return;

    if (!isAuthenticated()) {
      try {
        await GuestDocuments.assertCanUpload(state.guestSessionId, state.guestUploadLimit);
      } catch (err) {
        showToast(err.message);
        return;
      }
    }

    els.uploadAllBtn.disabled = true;
    let success = 0;

    for (const item of pending) {
      item.status = "uploading";
      item.progress = 0;
      renderFileList();

      try {
        if (isAuthenticated()) {
          const result = await API.uploadFile(item.file, (pct) => {
            item.progress = pct;
            if (pct >= 100 && item.status !== "indexing") {
              item.status = "indexing";
            }
            renderFileList();
          });
          item.status = "done";
          item.progress = 100;
          item.documentId = result.document_id;
        } else {
          const result = await API.processGuestFile(item.file, (pct) => {
            item.progress = pct;
            if (pct >= 100 && item.status !== "indexing") {
              item.status = "indexing";
            }
            renderFileList();
          });
          await GuestDocuments.save(state.guestSessionId, result, item.file);
          item.status = "done";
          item.progress = 100;
          item.documentId = result.document_id;
        }
        await refreshDocumentIdsFromServer();
        success++;
      } catch (err) {
        item.status = "error";
        item.error = err.message;
      }
      renderFileList();
    }

    showToast(`${success} of ${pending.length} file(s) indexed successfully`);
    els.uploadAllBtn.disabled = !state.pendingFiles.some((f) => f.status === "pending");

    if (success > 0 && !$("#documentsModal").classList.contains("hidden")) {
      openDocumentsModal();
    }
  }

  function clearFiles() {
    state.pendingFiles = state.pendingFiles.filter((f) => f.status === "uploading" || f.status === "indexing");
    renderFileList();
  }

  // ===== Search chats =====
  function searchChats(query) {
    const results = $("#chatSearchResults");
    results.innerHTML = "";
    const q = String(query || "").toLowerCase().trim();

    const matches = state.chats.filter((chat) => {
      if (!q) return true;
      const title = String(chat?.title || "").toLowerCase();
      if (title.includes(q)) return true;
      const messages = Array.isArray(chat?.messages) ? chat.messages : [];
      return messages.some((m) => String(m?.content || "").toLowerCase().includes(q));
    });

    if (!matches.length) {
      results.innerHTML = '<li style="color:var(--text-muted);cursor:default">No chats found</li>';
      return;
    }

    matches.forEach((chat) => {
      const li = document.createElement("li");
      li.textContent = chat.title;
      li.addEventListener("click", () => loadChat(chat.id));
      results.appendChild(li);
    });
  }

  function formatDate(iso) {
    if (!iso) return "Unknown date";
    try {
      return new Date(iso).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch {
      return iso;
    }
  }

  async function openDocumentsModal() {
    closeAllModals();
    openModal("documentsModal");

    const listEl = $("#documentsList");
    const countEl = $("#documentsCount");
    const emptyEl = $("#documentsEmpty");

    listEl.innerHTML = "";
    countEl.textContent = "Loading...";
    emptyEl.classList.add("hidden");

    try {
      let docs = [];
      if (isAuthenticated()) {
        const data = await API.listDocuments();
        docs = data.documents || [];
      } else if (state.guestSessionId) {
        docs = await GuestDocuments.list(state.guestSessionId);
      }

      countEl.textContent = docs.length
        ? `${docs.length} document${docs.length === 1 ? "" : "s"} indexed`
        : "No documents indexed";

      if (!docs.length) {
        emptyEl.classList.remove("hidden");
        return;
      }

      docs.forEach((doc) => {
        const li = document.createElement("li");
        li.className = "document-row";

        const canDownload = doc.source === "file";
        const icon = fileIcon(doc.filename);

        li.innerHTML = `
          <div class="document-row-icon">${icon}</div>
          <div class="document-row-info">
            <div class="document-row-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</div>
            <div class="document-row-meta">${escapeHtml(doc.source_type.toUpperCase())} · ${doc.chunk_count} chunks · ${formatDate(doc.created_at)}</div>
          </div>
          <div class="document-row-actions">
            <button class="document-download-btn" type="button" ${canDownload ? "" : "disabled title=\"Database sources are not downloadable\""}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Download
            </button>
            <button class="document-delete-btn" type="button" title="Delete from index">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
              Delete
            </button>
          </div>
        `;

        if (canDownload) {
          li.querySelector(".document-download-btn").addEventListener("click", async () => {
            if (isAuthenticated()) {
              window.location.href = API.documentDownloadUrl(doc.document_id);
              return;
            }
            try {
              const blob = await GuestDocuments.downloadBlob(state.guestSessionId, doc.document_id);
              if (!blob) {
                showToast("File not found locally");
                return;
              }
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = doc.filename;
              link.click();
              URL.revokeObjectURL(url);
            } catch (err) {
              showToast(err.message || "Download failed");
            }
          });
        }

        li.querySelector(".document-delete-btn").addEventListener("click", async () => {
          const ok = window.confirm(`Delete "${doc.filename}" from the index?`);
          if (!ok) return;

          try {
            if (isAuthenticated()) {
              await API.deleteDocument(doc.document_id);
            } else {
              await GuestDocuments.delete(state.guestSessionId, doc.document_id);
            }
            await refreshDocumentIdsFromServer();
            showToast("Document deleted from index");
            openDocumentsModal();
          } catch (err) {
            showToast(err.message || "Delete failed");
          }
        });

        listEl.appendChild(li);
      });
    } catch (err) {
      countEl.textContent = "Failed to load documents";
      showToast(err.message);
    }
  }

  // ===== Brand menu actions =====
  async function handleBrandAction(action) {
    closeAllModals();
    $("#brandMenu")?.classList.add("hidden");
    switch (action) {
      case "about":
        openModal("aboutModal");
        break;
      case "documents":
        openDocumentsModal();
        break;
    }
  }

  // ===== Event bindings =====
  function bindEvents() {
    // Sidebar
    $("#newChatBtn").addEventListener("click", () => { newChat(); if (isMobile()) closeSidebar(); });
    $("#searchChatsBtn").addEventListener("click", () => {
      openModal("searchModal");
      $("#chatSearchInput").focus();
      searchChats("");
      if (isMobile()) closeSidebar();
    });
    $("#uploadsBtn").addEventListener("click", () => { openModal("uploadModal"); if (isMobile()) closeSidebar(); });
    $("#attachBtn").addEventListener("click", () => openModal("uploadModal"));
    $("#featuresBtn").addEventListener("click", () => { openModal("featuresModal"); if (isMobile()) closeSidebar(); });
    $("#settingsBtn").addEventListener("click", () => { openModal("settingsModal"); if (isMobile()) closeSidebar(); });
    $("#helpBtn").addEventListener("click", () => { openModal("helpModal"); if (isMobile()) closeSidebar(); });
    els.loginBtn.addEventListener("click", () => openModal("loginModal"));
    els.registerBtn.addEventListener("click", () => openModal("registerModal"));
    els.logoutBtn.addEventListener("click", async () => {
      try {
        await API.logout();
      } catch {
        // Ignore logout API failures and clear auth cookies.
      }
      state.authUser = null;
      try {
        GuestStorage.clear();
        if (state.guestSessionId) {
          await GuestDocuments.clear(state.guestSessionId);
        }
        await API.purgeSession();
        await bootstrapGuest();
      } catch {
        state.chats = [];
        state.documentIds = [];
        state.guestSessionId = null;
      }
      renderAuthState();
      renderChatHistory();
      renderMessages();
      showToast("Logged out");
    });

    els.sidebarPanelBtn.addEventListener("click", toggleSidebar);
    els.hamburgerBtn.addEventListener("click", toggleSidebar);
    els.sidebarClose.addEventListener("click", closeSidebar);
    els.sidebarBackdrop.addEventListener("click", closeSidebar);

    window.addEventListener("resize", () => {
      initSidebarLayout();
    });

    // Theme
    els.themeToggle.addEventListener("click", cycleTheme);
    els.themeSelect.addEventListener("change", (e) => {
      state.settings.theme = e.target.value;
      applyTheme(state.settings.theme);
      persistPreferences();
    });

    // Settings
    $("#clearHistoryBtn").addEventListener("click", async () => {
      state.chats = [];
      setActiveChatId(null);
      if (!isAuthenticated()) {
        GuestStorage.clear();
        if (state.guestSessionId) {
          await GuestDocuments.clear(state.guestSessionId);
          await refreshDocumentIdsFromServer();
        }
      }
      saveChats();
      renderChatHistory();
      renderMessages();
      closeModal("settingsModal");
      showToast("Chat history cleared");
    });

    // Brand dropdown
    $("#brandBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      $("#brandMenu").classList.toggle("hidden");
    });

    $("#brandMenu").querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => handleBrandAction(btn.dataset.action));
    });

    // Chat form
    els.chatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      sendMessage();
    });

    els.chatInput.addEventListener("input", () => {
      autoResizeInput();
      updateSendBtn();
    });

    els.chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Upload modal
    $("#uploadModalClose").addEventListener("click", () => closeModal("uploadModal"));
    $("#browseFilesBtn").addEventListener("click", () => els.fileInput.click());
    els.fileInput.addEventListener("change", (e) => {
      addFiles(e.target.files);
      e.target.value = "";
    });
    $("#uploadAllBtn").addEventListener("click", uploadAll);
    $("#clearFilesBtn").addEventListener("click", clearFiles);

    els.dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      els.dropzone.classList.add("dragover");
    });
    els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("dragover"));
    els.dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      els.dropzone.classList.remove("dragover");
      addFiles(e.dataTransfer.files);
    });

    // Generic modal close
    $$("[data-close]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(btn.dataset.close));
    });

    $$(".modal-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeModal(overlay.id);
      });
    });

    $$("[data-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeAllModals();
        openModal(btn.dataset.open);
      });
    });

    $("#viewDocumentsBtn").addEventListener("click", () => {
      closeModal("featuresModal");
      openDocumentsModal();
    });

    $("#loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = $("#loginEmail").value.trim();
      const password = $("#loginPassword").value;
      try {
        const result = await API.login(email, password);
        state.authUser = result.user || null;
        await bootstrapAuth();
        renderAuthState();
        closeModal("loginModal");
        showToast("Logged in");
      } catch (err) {
        showToast(err.message || "Login failed");
      }
    });

    $("#registerForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = $("#registerEmail").value.trim();
      const password = $("#registerPassword").value;
      const website = ($("#registerWebsite") && $("#registerWebsite").value) || "";
      try {
        await API.register(email, password, website);
        const result = await API.login(email, password);
        state.authUser = result.user || null;
        await bootstrapAuth();
        renderAuthState();
        closeModal("registerModal");
        showToast("Account created");
      } catch (err) {
        showToast(err.message || "Registration failed");
      }
    });

    // Search
    $("#chatSearchInput").addEventListener("input", (e) => searchChats(e.target.value));

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case "k":
            e.preventDefault();
            openModal("searchModal");
            $("#chatSearchInput").focus();
            break;
          case "u":
            e.preventDefault();
            openModal("uploadModal");
            break;
          case "n":
            e.preventDefault();
            newChat();
            break;
        }
      }
      if (e.key === "Escape") closeAllModals();
    });

    document.addEventListener("click", () => $("#brandMenu")?.classList.add("hidden"));
  }

  // ===== Init =====
  async function init() {
    API.clearLegacyLocalStorage();
    loadState();
    initTheme();
    initSidebarLayout();
    initMobileViewport();

    if (!state.activeChatId && state.chats.length) {
      state.activeChatId = state.chats[0].id;
    }

    renderChatHistory();
    renderMessages();
    bindEvents();
    await bootstrapAuth();
    updateSendBtn();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
