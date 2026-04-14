import { apiGet } from './client';

export interface BackendHealthResponse {
  status: string;
  timestamp: string;
  components: {
    database: string;
    chroma_db: string;
    kg_jsonl: string;
    mineru_api: string;
    agentic_rag: string;
  };
  document_stats: {
    total: number;
    ready: number;
    indexing: number;
    parsing: number;
    failed: number;
  };
}

export const healthApi = {
  check: () => apiGet<BackendHealthResponse>('/health', 10000),
};
