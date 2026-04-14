import { apiGet, apiUpload, apiDelete } from './client';

/* ── 后端返回类型（对齐 backend/models.py）─────────────────── */

export interface BackendDocumentStatus {
  doc_id: string;
  filename: string;
  file_type: string;
  status: string;
  mineru_api_type: string | null;
  vector_status: string | null;
  kg_status: string | null;
  chunk_count: number | null;
  entity_count: number | null;
  error_msg: string | null;
  created_at: string;
  updated_at: string;
  ready_for_qa: boolean;
}

export interface BackendDocumentListItem {
  doc_id: string;
  filename: string;
  file_type: string;
  status: string;
  chunk_count: number | null;
  entity_count: number | null;
  created_at: string;
}

export interface BackendDocumentListResponse {
  total: number;
  limit: number;
  offset: number;
  documents: BackendDocumentListItem[];
}

export interface BackendUploadResponse {
  doc_id: string;
  filename: string;
  file_type: string;
  status: string;
  message: string;
}

/* ── API 封装 ────────────────────────────────────────────── */

export const documentsApi = {
  /** 获取文档列表，可按状态过滤 */
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiGet<BackendDocumentListResponse>(`/documents${query ? `?${query}` : ''}`);
  },

  /** 查询单个文档状态 */
  getStatus: (docId: string) =>
    apiGet<BackendDocumentStatus>(`/documents/${docId}/status`),

  /** 上传文件 */
  upload: (file: File, enableOcr = true) => {
    const form = new FormData();
    form.append('file', file);
    form.append('enable_ocr', String(enableOcr));
    return apiUpload<BackendUploadResponse>('/documents/upload', form, 30000);
  },

  /** 删除文档 */
  delete: (docId: string) =>
    apiDelete<{ message: string; doc_id: string }>(`/documents/${docId}`),
};
