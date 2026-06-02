/**
 * Nano RAG — API client (HttpOnly cookies + CSRF double-submit)
 */
const API = {
  base: "",
  sessionCookie: "nano_session_id",
  csrfAccessCookie: "csrf_access_token",
  csrfRefreshCookie: "csrf_refresh_token",

  getCookie(name) {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
  },

  csrfHeaders(path, method = "GET") {
    const verb = method.toUpperCase();
    if (verb === "GET" || verb === "HEAD") return {};
    const isRefresh = path.includes("/auth/refresh") || path.includes("/auth/logout");
    const cookieName = isRefresh ? this.csrfRefreshCookie : this.csrfAccessCookie;
    const token = this.getCookie(cookieName);
    return token ? { "X-CSRF-TOKEN": token } : {};
  },

  clearLegacyLocalStorage() {
    const legacyKeys = [
      "nano_session_id",
      "nano_access_token",
      "nano_refresh_token",
      "nano_document_ids",
      "nano_chats_guest",
      "nano_active_chat_guest",
      "nano_active_chat_auth",
      "nano_settings",
      "nano_theme",
      "nano_chats",
    ];
    for (const key of legacyKeys) {
      try {
        localStorage.removeItem(key);
      } catch (_) {
        /* ignore */
      }
    }
  },

  clearLegacyAuthCookies() {
    const legacy = ["nano_access_token", "nano_refresh_token"];
    for (const name of legacy) {
      document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
    }
  },

  async purgeSession() {
    await fetch(`${this.base}/api/session`, {
      method: "DELETE",
      credentials: "include",
      headers: this.csrfHeaders("/api/session", "DELETE"),
    });
  },

  async syncSession() {
    this.clearLegacyLocalStorage();
    this.clearLegacyAuthCookies();
    await this.ensureSession();
  },

  async request(path, options = {}) {
    const method = options.method || "GET";
    const headers = {
      ...(options.headers || {}),
      ...this.csrfHeaders(path, method),
    };
    const res = await fetch(`${this.base}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
    const contentType = res.headers.get("content-type") || "";

    if (!res.ok) {
      let message = `Request failed (${res.status})`;
      if (contentType.includes("application/json")) {
        const data = await res.json();
        message = data.error || message;
      }
      throw new Error(message);
    }

    if (contentType.includes("application/json")) {
      return res.json();
    }
    return res.text();
  },

  health() {
    return this.request("/api/health");
  },

  ensureSession() {
    return this.request("/api/session");
  },

  getPreferences() {
    return this.request("/api/preferences");
  },

  savePreferences(preferences) {
    return this.request("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preferences),
    });
  },

  register(email, password, website = "") {
    return this.request("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, website }),
    });
  },

  login(email, password) {
    return this.request("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  },

  me() {
    return this.request("/api/auth/me");
  },

  async logout() {
    try {
      await this.request("/api/auth/logout", { method: "POST" });
    } finally {
      this.clearLegacyAuthCookies();
    }
  },

  listDocuments() {
    return this.request("/api/documents");
  },

  listChats() {
    return this.request("/api/chats");
  },

  saveChat(chat) {
    return this.request(`/api/chats/${chat.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chat),
    });
  },

  deleteChat(chatId) {
    return this.request(`/api/chats/${chatId}`, { method: "DELETE" });
  },

  documentDownloadUrl(documentId) {
    return `${this.base}/api/documents/${documentId}/download`;
  },

  documentText(documentId, start = 0, end = 0, full = false) {
    const qs = new URLSearchParams({
      start: String(start ?? 0),
      end: String(end ?? start ?? 0),
    });
    if (full) qs.set("full", "1");
    return this.request(`/api/documents/${documentId}/text?${qs.toString()}`);
  },

  deleteDocument(id) {
    return this.request(`/api/documents/${id}`, { method: "DELETE" });
  },

  search(query, topK = 20, documentIds = null) {
    return this.request("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK, document_ids: documentIds || undefined }),
    });
  },

  async chatStream(query, topK = 5, onToken, onSources, documentIds = null, contextChunks = null) {
    const body = {
      query,
      top_k: topK,
      document_ids: documentIds || undefined,
    };
    if (contextChunks?.length) {
      body.context_chunks = contextChunks;
    }

    const res = await fetch(`${this.base}/api/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...this.csrfHeaders("/api/chat/stream", "POST"),
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `Chat failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";
    let sources = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") return { text: fullText, sources };

        try {
          const parsed = JSON.parse(payload);
          if (parsed.error) throw new Error(parsed.error);
          if (parsed.sources) {
            sources = parsed.sources;
            if (onSources) onSources(sources);
          }
          if (parsed.token) {
            fullText += parsed.token;
            if (onToken) onToken(parsed.token, fullText);
          }
        } catch (e) {
          if (e.message && !e.message.includes("JSON")) throw e;
        }
      }
    }
    return { text: fullText, sources };
  },

  uploadFile(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file);

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      xhr.addEventListener("load", () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(data);
          } else {
            reject(new Error(data.error || "Upload failed"));
          }
        } catch {
          reject(new Error("Upload failed"));
        }
      });

      xhr.addEventListener("error", () => reject(new Error("Network error")));
      xhr.open("POST", `${this.base}/api/ingest/files`);
      xhr.withCredentials = true;
      const csrf = this.csrfHeaders("/api/ingest/files", "POST");
      if (csrf["X-CSRF-TOKEN"]) {
        xhr.setRequestHeader("X-CSRF-TOKEN", csrf["X-CSRF-TOKEN"]);
      }
      xhr.send(form);
    });
  },

  processGuestFile(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file);

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      xhr.addEventListener("load", () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(data);
          } else {
            reject(new Error(data.error || "Processing failed"));
          }
        } catch {
          reject(new Error("Processing failed"));
        }
      });

      xhr.addEventListener("error", () => reject(new Error("Network error")));
      xhr.open("POST", `${this.base}/api/ingest/process`);
      xhr.withCredentials = true;
      const csrf = this.csrfHeaders("/api/ingest/process", "POST");
      if (csrf["X-CSRF-TOKEN"]) {
        xhr.setRequestHeader("X-CSRF-TOKEN", csrf["X-CSRF-TOKEN"]);
      }
      xhr.send(form);
    });
  },

  embedQuery(text) {
    return this.request("/api/embed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((data) => data.embedding || []);
  },

  rankChunks(query, candidates, topK = 5) {
    return this.request("/api/retrieval/rank", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, candidates, top_k: topK }),
    }).then((data) => data.results || []);
  },
};
