import { create } from "zustand";
import { documentsApi, BackendDocumentStatus } from "./api/documents";

/* ── Document 类型（前端视图层）────────────────────────────── */

export type DocumentStatus =
  | "UPLOADED"
  | "PARSING"
  | "PARSED"
  | "INDEXING"
  | "READY"
  | "PARSE_FAILED"
  | "INDEX_FAILED";

export interface Document {
  id: string;          // = backend doc_id
  name: string;        // = backend filename
  type: string;        // = backend file_type（大写）
  status: DocumentStatus;
  uploadTime: string;  // = backend created_at
  chunks?: number;     // = backend chunk_count
  entities?: number;   // = backend entity_count
  vectorStatus?: string; // = backend vector_status
  kgStatus?: string;     // = backend kg_status
  errorMsg?: string;   // = backend error_msg
  // 派生进度值（前端根据子状态估算）
  vectorProgress?: number;
  kgProgress?: number;
}

/** 将后端 DocumentStatus API 响应映射到前端 Document */
export function mapBackendStatus(s: BackendDocumentStatus): Document {
  const vectorPct =
    s.vector_status === "done" ? 100 : s.vector_status === "building" ? 50 : 0;
  const kgPct =
    s.kg_status === "done" ? 100 : s.kg_status === "building" ? 50 : 0;

  return {
    id: s.doc_id,
    name: s.filename,
    type: s.file_type.toUpperCase(),
    status: s.status as DocumentStatus,
    uploadTime: s.created_at,
    chunks: s.chunk_count ?? undefined,
    entities: s.entity_count ?? undefined,
    vectorStatus: s.vector_status ?? undefined,
    kgStatus: s.kg_status ?? undefined,
    errorMsg: s.error_msg ?? undefined,
    vectorProgress: vectorPct,
    kgProgress: kgPct,
  };
}

/* ── DocumentStore ──────────────────────────────────────── */

const TERMINAL_STATUSES = new Set(["READY", "PARSE_FAILED", "INDEX_FAILED"]);
const POLL_INTERVAL_MS = 5000;

interface DocumentStore {
  documents: Document[];
  selectedDocIds: string[];
  loading: boolean;

  // Actions
  fetchDocuments: () => Promise<void>;
  addDocument: (doc: Document) => void;
  updateDocument: (id: string, updates: Partial<Document>) => void;
  removeDocument: (id: string) => void;
  toggleDocSelection: (id: string) => void;
  toggleAllSelection: (ids: string[]) => void;

  // Polling
  startPolling: (docId: string) => void;
  stopPolling: (docId: string) => void;
  _pollingTimers: Record<string, ReturnType<typeof setInterval>>;
}

export const useDocumentStore = create<DocumentStore>((set, get) => ({
  documents: [],
  selectedDocIds: [],
  loading: false,
  _pollingTimers: {},

  fetchDocuments: async () => {
    set({ loading: true });
    try {
      const res = await documentsApi.list({ limit: 100 });
      const docs: Document[] = res.documents.map((d) => ({
        id: d.doc_id,
        name: d.filename,
        type: d.file_type.toUpperCase(),
        status: d.status as DocumentStatus,
        uploadTime: d.created_at,
        chunks: d.chunk_count ?? undefined,
        entities: d.entity_count ?? undefined,
      }));
      set({ documents: docs, loading: false });

      // 对仍在处理中的文档启动轮询
      docs.forEach((doc) => {
        if (!TERMINAL_STATUSES.has(doc.status)) {
          get().startPolling(doc.id);
        }
      });
    } catch {
      set({ loading: false });
    }
  },

  addDocument: (doc) =>
    set((state) => ({ documents: [doc, ...state.documents] })),

  updateDocument: (id, updates) =>
    set((state) => ({
      documents: state.documents.map((d) =>
        d.id === id ? { ...d, ...updates } : d
      ),
    })),

  removeDocument: (id) =>
    set((state) => ({
      documents: state.documents.filter((d) => d.id !== id),
      selectedDocIds: state.selectedDocIds.filter((sid) => sid !== id),
    })),

  toggleDocSelection: (id) =>
    set((state) => ({
      selectedDocIds: state.selectedDocIds.includes(id)
        ? state.selectedDocIds.filter((sid) => sid !== id)
        : [...state.selectedDocIds, id],
    })),

  toggleAllSelection: (ids) =>
    set((state) => ({
      selectedDocIds:
        state.selectedDocIds.length === ids.length ? [] : ids,
    })),

  startPolling: (docId) => {
    const { _pollingTimers, stopPolling, updateDocument } = get();
    if (_pollingTimers[docId]) return; // already polling

    const timer = setInterval(async () => {
      try {
        const s = await documentsApi.getStatus(docId);
        updateDocument(docId, mapBackendStatus(s));
        if (TERMINAL_STATUSES.has(s.status)) {
          stopPolling(docId);
        }
      } catch {
        // silently ignore transient errors during polling
      }
    }, POLL_INTERVAL_MS);

    set((state) => ({
      _pollingTimers: { ...state._pollingTimers, [docId]: timer },
    }));
  },

  stopPolling: (docId) => {
    const { _pollingTimers } = get();
    if (_pollingTimers[docId]) {
      clearInterval(_pollingTimers[docId]);
      set((state) => {
        const timers = { ...state._pollingTimers };
        delete timers[docId];
        return { _pollingTimers: timers };
      });
    }
  },
}));

/* ── KG / Passage 类型（对齐后端）──────────────────────────── */

export interface KGEntity {
  name: string;
  type: string;
  attributes: Record<string, string>;
  context_snippet: string;
  document_id: string;
}

export interface Passage {
  id: string;
  content: string;
  section: string;
  page: number;
  chunk_type: "text" | "table";
  entities: string[];
  document_id: string;
}

export interface MessageMeta {
  route: "entity_query" | "semantic_query" | "hybrid_query" | "direct_answer";
  rewrite_count: number;
  sufficient: boolean;
  latency_ms: number;
  question_used?: string;
  original_question?: string;
}

export interface MessageSources {
  kg_entities: KGEntity[];
  passages: Passage[];
}

export interface Message {
  id: string;
  role: "user" | "ai";
  content: string;
  timestamp: string;
  meta?: MessageMeta;
  sources?: MessageSources;
  isLoading?: boolean;
}

/* ── ChatStore ───────────────────────────────────────────── */

interface ChatStore {
  messages: Message[];
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  currentSources: MessageSources | null;
  setCurrentSources: (sources: MessageSources | null) => void;
  currentMeta: MessageMeta | null;
  setCurrentMeta: (meta: MessageMeta | null) => void;
  isSourcePanelOpen: boolean;
  toggleSourcePanel: (open?: boolean) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),
  updateMessage: (id, updates) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    })),
  currentSources: null,
  setCurrentSources: (sources) => set({ currentSources: sources }),
  currentMeta: null,
  setCurrentMeta: (meta) => set({ currentMeta: meta }),
  isSourcePanelOpen: false,
  toggleSourcePanel: (open) =>
    set((state) => ({
      isSourcePanelOpen:
        open !== undefined ? open : !state.isSourcePanelOpen,
    })),
  clearMessages: () => set({ messages: [], currentSources: null, currentMeta: null }),
}));
