import { apiPost } from './client';

/* ── 后端返回类型（对齐 backend/models.py）─────────────────── */

export interface BackendKGEntity {
  name: string;
  type: string;
  attributes: Record<string, string>;
  context_snippet: string;
  document_id: string;
}

export interface BackendPassage {
  content: string;
  section: string;
  page: number;
  document_id: string;
  chunk_type: string;
  entities: string[];
  char_range: [number, number] | null;
}

export interface BackendQAMeta {
  route: string;
  rewrite_count: number;
  question_used: string;
  original_question: string;
  sufficient: boolean;
  latency_ms: number;
}

export interface BackendQAResponse {
  answer: string;
  meta: BackendQAMeta;
  sources: {
    kg_entities: BackendKGEntity[];
    passages: BackendPassage[];
  };
  session_id: string | null;
}

/* ── API 封装 ────────────────────────────────────────────── */

export const qaApi = {
  /** 发起问答请求（最长 135s，后端超时 120s + 缓冲） */
  query: (question: string, docIds?: string[], sessionId?: string | null) =>
    apiPost<BackendQAResponse>(
      '/qa/query',
      {
        question,
        doc_ids: docIds && docIds.length > 0 ? docIds : null,
        session_id: sessionId ?? null,
      },
      135000,
    ),
};
