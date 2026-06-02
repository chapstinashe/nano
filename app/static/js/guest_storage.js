/**
 * Encrypted sessionStorage for guest (unauthenticated) chat history.
 * Data survives page refresh but is cleared when the tab/window closes.
 * Key is derived from the guest session id returned by /api/session.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "nano_guest_chats_enc_v1";
  const LEGACY_KEYS = [
    "nano_chats_guest",
    "nano_active_chat_guest",
    "nano_guest_chats_enc_v1",
  ];
  const PBKDF2_ITERATIONS = 310000;
  const SALT_BYTES = new TextEncoder().encode("nano-rag-guest-storage-v1");

  function toBase64(bytes) {
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary);
  }

  function fromBase64(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  async function deriveKey(sessionId) {
    if (!sessionId) {
      throw new Error("Session is required for guest storage");
    }
    if (!window.crypto?.subtle) {
      throw new Error("Secure encryption is not available in this browser");
    }

    const baseKey = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(sessionId),
      "PBKDF2",
      false,
      ["deriveKey"]
    );

    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt: SALT_BYTES,
        iterations: PBKDF2_ITERATIONS,
        hash: "SHA-256",
      },
      baseKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  async function encryptPayload(sessionId, data) {
    const key = await deriveKey(sessionId);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const plaintext = new TextEncoder().encode(JSON.stringify(data));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
    return {
      v: 1,
      iv: toBase64(iv),
      data: toBase64(new Uint8Array(ciphertext)),
    };
  }

  async function decryptPayload(sessionId, envelope) {
    if (!envelope || envelope.v !== 1 || !envelope.iv || !envelope.data) {
      return null;
    }
    const key = await deriveKey(sessionId);
    const iv = fromBase64(envelope.iv);
    const ciphertext = fromBase64(envelope.data);
    const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ciphertext);
    return JSON.parse(new TextDecoder().decode(plaintext));
  }

  function removeLegacyLocalStorage() {
    for (const key of LEGACY_KEYS) {
      try {
        localStorage.removeItem(key);
      } catch (_) {
        /* ignore */
      }
    }
  }

  window.GuestStorage = {
    STORAGE_KEY,

    clearLegacy() {
      removeLegacyLocalStorage();
    },

    async load(sessionId) {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return { chats: [], activeChatId: null };
      }

      try {
        const envelope = JSON.parse(raw);
        const payload = await decryptPayload(sessionId, envelope);
        if (!payload || typeof payload !== "object") {
          return { chats: [], activeChatId: null };
        }
        return {
          chats: Array.isArray(payload.chats) ? payload.chats : [],
          activeChatId: payload.activeChatId || null,
        };
      } catch (_) {
        return { chats: [], activeChatId: null };
      }
    },

    async save(sessionId, { chats, activeChatId }) {
      const envelope = await encryptPayload(sessionId, { chats, activeChatId });
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(envelope));
    },

    clear() {
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch (_) {
        /* ignore */
      }
      removeLegacyLocalStorage();
    },
  };
})();
