import { create } from "zustand";

export type DocumentStatus = "UPLOADED" | "PARSING" | "PARSED" | "INDEXING" | "READY" | "PARSE_FAILED" | "INDEX_FAILED";

export interface Document {
  id: string;
  name: string;
  type: string;
  size: number;
  status: DocumentStatus;
  uploadTime: string;
  finishTime?: string;
  chunks?: number;
  entities?: number;
  vectorProgress?: number;
  kgProgress?: number;
  errorMsg?: string;
}

interface DocumentStore {
  documents: Document[];
  selectedDocIds: string[];
  addDocument: (doc: Document) => void;
  updateDocument: (id: string, updates: Partial<Document>) => void;
  removeDocument: (id: string) => void;
  toggleDocSelection: (id: string) => void;
  toggleAllSelection: (ids: string[]) => void;
}

export const useDocumentStore = create<DocumentStore>((set) => ({
  documents: [
    {
      id: "doc-1",
      name: "技术报告-Q1-2026.pdf",
      type: "PDF",
      size: 12400000,
      status: "READY",
      uploadTime: "2026-04-13T10:00:00Z",
      finishTime: "2026-04-13T10:12:45Z",
      chunks: 15,
      entities: 130,
    },
    {
      id: "doc-2",
      name: "销售数据统计.xlsx",
      type: "XLSX",
      size: 2048000,
      status: "INDEXING",
      uploadTime: "2026-04-13T10:30:00Z",
      vectorProgress: 80,
      kgProgress: 100,
    },
    {
      id: "doc-3",
      name: "产品架构图.jpg",
      type: "JPG",
      size: 500000,
      status: "PARSE_FAILED",
      uploadTime: "2026-04-13T09:45:00Z",
      errorMsg: "解析超时（>600s）",
    }
  ],
  selectedDocIds: ["doc-1"],
  addDocument: (doc) => set((state) => ({ documents: [doc, ...state.documents] })),
  updateDocument: (id, updates) => set((state) => ({
    documents: state.documents.map((d) => d.id === id ? { ...d, ...updates } : d)
  })),
  removeDocument: (id) => set((state) => ({
    documents: state.documents.filter((d) => d.id !== id),
    selectedDocIds: state.selectedDocIds.filter((sid) => sid !== id)
  })),
  toggleDocSelection: (id) => set((state) => ({
    selectedDocIds: state.selectedDocIds.includes(id) 
      ? state.selectedDocIds.filter(sid => sid !== id)
      : [...state.selectedDocIds, id]
  })),
  toggleAllSelection: (ids) => set((state) => ({
    selectedDocIds: state.selectedDocIds.length === ids.length ? [] : ids
  }))
}));

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

interface ChatStore {
  messages: Message[];
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  currentSources: MessageSources | null;
  setCurrentSources: (sources: MessageSources | null) => void;
  isSourcePanelOpen: boolean;
  toggleSourcePanel: (open?: boolean) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  updateMessage: (id, updates) => set((state) => ({
    messages: state.messages.map(m => m.id === id ? { ...m, ...updates } : m)
  })),
  currentSources: null,
  setCurrentSources: (sources) => set({ currentSources: sources }),
  isSourcePanelOpen: false,
  toggleSourcePanel: (open) => set((state) => ({ 
    isSourcePanelOpen: open !== undefined ? open : !state.isSourcePanelOpen 
  })),
}));
