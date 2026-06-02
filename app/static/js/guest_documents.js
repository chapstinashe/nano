/**
 * IndexedDB storage for guest uploads, extracted text, and chunk embeddings.
 * Embeddings never touch server Cosmos — only returned transiently from /api/ingest/process.
 */
(function () {
  "use strict";

  const DB_NAME = "nano_guest_documents_v2";
  const DB_VERSION = 1;
  const DOCS_STORE = "documents";
  const CHUNKS_STORE = "chunk_embeddings";
  let dbPromise = null;

  function openDb() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(DOCS_STORE)) {
          const docs = db.createObjectStore(DOCS_STORE, { keyPath: "document_id" });
          docs.createIndex("session_id", "session_id", { unique: false });
          docs.createIndex("created_at", "created_at", { unique: false });
        }
        if (!db.objectStoreNames.contains(CHUNKS_STORE)) {
          const chunks = db.createObjectStore(CHUNKS_STORE, { keyPath: "id" });
          chunks.createIndex("session_id", "session_id", { unique: false });
          chunks.createIndex("document_id", "document_id", { unique: false });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("IndexedDB open failed"));
    });
    return dbPromise;
  }

  function txPromise(db, storeNames, mode, fn) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeNames, mode);
      fn(tx);
      tx.oncomplete = () => resolve(undefined);
      tx.onerror = () => reject(tx.error || new Error("IndexedDB transaction failed"));
      tx.onabort = () => reject(tx.error || new Error("IndexedDB transaction aborted"));
    });
  }

  function normalizeChunks(chunks, documentId) {
    if (!Array.isArray(chunks) || !chunks.length) {
      throw new Error("Processed file did not return chunk embeddings");
    }
    return chunks.map((chunk, index) => {
      const embedding = chunk.embedding;
      if (!Array.isArray(embedding) || !embedding.length) {
        throw new Error(`Missing embedding for chunk ${index}`);
      }
      return {
        id: chunk.id || `${documentId}_${index}`,
        text: chunk.text || "",
        embedding,
        metadata: chunk.metadata || {},
      };
    });
  }

  function cosineSimilarity(a, b) {
    if (!a?.length || !b?.length || a.length !== b.length) return 0;
    let dot = 0;
    let normA = 0;
    let normB = 0;
    for (let i = 0; i < a.length; i += 1) {
      dot += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }
    if (!normA || !normB) return 0;
    return dot / (Math.sqrt(normA) * Math.sqrt(normB));
  }

  function startOfUtcDay(iso) {
    const date = iso ? new Date(iso) : new Date();
    return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  }

  window.GuestDocuments = {
    DOCS_STORE,
    CHUNKS_STORE,

    async list(sessionId) {
      const db = await openDb();
      const docs = await new Promise((resolve, reject) => {
        const tx = db.transaction(DOCS_STORE, "readonly");
        const req = tx.objectStore(DOCS_STORE).getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      });
      return docs
        .filter((doc) => doc.session_id === sessionId)
        .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
        .map((doc) => ({
          document_id: doc.document_id,
          filename: doc.filename,
          source_type: doc.source_type,
          chunk_count: doc.chunk_count,
          created_at: doc.created_at,
          source: doc.source || "file",
        }));
    },

    async get(sessionId, documentId) {
      const db = await openDb();
      const doc = await new Promise((resolve, reject) => {
        const tx = db.transaction(DOCS_STORE, "readonly");
        const req = tx.objectStore(DOCS_STORE).get(documentId);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
      if (!doc || doc.session_id !== sessionId) return null;
      return doc;
    },

    async save(sessionId, payload, file) {
      const normalizedChunks = normalizeChunks(payload.chunks, payload.document_id);
      const buffer = await file.arrayBuffer();
      const record = {
        session_id: sessionId,
        document_id: payload.document_id,
        filename: payload.filename,
        source_type: payload.source_type,
        chunk_count: normalizedChunks.length,
        created_at: payload.created_at,
        source: payload.source || "file",
        text: payload.text || "",
        file_name: file.name,
        file_type: file.type || "application/octet-stream",
        file_data: buffer,
      };

      const db = await openDb();
      await txPromise(db, [DOCS_STORE, CHUNKS_STORE], "readwrite", (tx) => {
        tx.objectStore(DOCS_STORE).put(record);
        const chunkStore = tx.objectStore(CHUNKS_STORE);
        for (const chunk of normalizedChunks) {
          chunkStore.put({
            id: chunk.id,
            session_id: sessionId,
            document_id: payload.document_id,
            text: chunk.text,
            embedding: chunk.embedding,
            metadata: chunk.metadata,
          });
        }
      });

      return { ...record, chunks: normalizedChunks };
    },

    async delete(sessionId, documentId) {
      const doc = await this.get(sessionId, documentId);
      if (!doc) return false;

      const db = await openDb();
      await txPromise(db, [DOCS_STORE, CHUNKS_STORE], "readwrite", (tx) => {
        tx.objectStore(DOCS_STORE).delete(documentId);
        const chunkStore = tx.objectStore(CHUNKS_STORE);
        const index = chunkStore.index("document_id");
        const req = index.openCursor(IDBKeyRange.only(documentId));
        req.onsuccess = () => {
          const cursor = req.result;
          if (cursor) {
            if (cursor.value.session_id === sessionId) {
              cursor.delete();
            }
            cursor.continue();
          }
        };
      });
      return true;
    },

    async countUploadsToday(sessionId) {
      const docs = await this.list(sessionId);
      const today = startOfUtcDay();
      return docs.filter((doc) => startOfUtcDay(doc.created_at) === today).length;
    },

    async assertCanUpload(sessionId, dailyLimit) {
      const count = await this.countUploadsToday(sessionId);
      if (count >= dailyLimit) {
        const unit = dailyLimit === 1 ? "file" : "files";
        throw new Error(
          `Daily upload limit reached. You can upload only ${dailyLimit} ${unit} per day. Login to upload more files.`
        );
      }
    },

    async listDocumentIds(sessionId) {
      const docs = await this.list(sessionId);
      return docs.map((doc) => doc.document_id);
    },

    async search(sessionId, query, queryEmbedding, topK = 5, documentIds = null) {
      const db = await openDb();
      const chunks = await new Promise((resolve, reject) => {
        const tx = db.transaction(CHUNKS_STORE, "readonly");
        const req = tx.objectStore(CHUNKS_STORE).getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      });

      const allowed = documentIds ? new Set(documentIds) : null;
      const candidates = [];

      for (const chunk of chunks) {
        if (chunk.session_id !== sessionId) continue;
        if (allowed && !allowed.has(chunk.document_id)) continue;
        const vectorScore = cosineSimilarity(queryEmbedding, chunk.embedding || []);
        candidates.push({
          id: chunk.id,
          text: chunk.text,
          vector_score: vectorScore,
          metadata: chunk.metadata || {},
        });
      }

      if (!candidates.length) {
        return [];
      }

      candidates.sort((a, b) => b.vector_score - a.vector_score);
      const pool = candidates.slice(0, Math.max(topK * 4, 24));

      const ranked = await API.rankChunks(query, pool, topK);
      return ranked.map((result) => ({
        id: result.id,
        text: result.text,
        score: result.score,
        metadata: result.metadata || {},
      }));
    },

    async getText(sessionId, documentId) {
      const doc = await this.get(sessionId, documentId);
      if (!doc) return null;
      return {
        text: doc.text || "",
        filename: doc.filename || "Document",
      };
    },

    async downloadBlob(sessionId, documentId) {
      const doc = await this.get(sessionId, documentId);
      if (!doc?.file_data) return null;
      return new Blob([doc.file_data], {
        type: doc.file_type || "application/octet-stream",
      });
    },

    async clear(sessionId) {
      const db = await openDb();
      await txPromise(db, [DOCS_STORE, CHUNKS_STORE], "readwrite", (tx) => {
        for (const storeName of [DOCS_STORE, CHUNKS_STORE]) {
          const store = tx.objectStore(storeName);
          const req = store.openCursor();
          req.onsuccess = () => {
            const cursor = req.result;
            if (!cursor) return;
            if (!sessionId || cursor.value.session_id === sessionId) {
              cursor.delete();
            }
            cursor.continue();
          };
        }
      });
    },

    async clearAll() {
      const db = await openDb();
      await txPromise(db, [DOCS_STORE, CHUNKS_STORE], "readwrite", (tx) => {
        tx.objectStore(DOCS_STORE).clear();
        tx.objectStore(CHUNKS_STORE).clear();
      });
    },
  };
})();
