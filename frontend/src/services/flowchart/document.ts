import type { DiagramEdge, DiagramNode } from '@/models/flowchart';
import { request } from '@umijs/max';
import type { FlowchartResult, FlowchartTaskStatus } from './task';
import type { FlowchartDiagramTheme, FlowchartDirection } from './workbench';

export type MermaidCompilationStatus =
  | 'idle'
  | 'compiling'
  | 'ready'
  | 'failed';

export interface MermaidCompilation {
  version: number;
  status: MermaidCompilationStatus;
  errorCode?: string | null;
  errorMessage?: string | null;
}

export interface FlowchartDocument {
  id: string;
  title: string;
  direction: FlowchartDirection;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  mermaidSource: string;
  metadata: {
    version: number;
    generatedBy?: string | null;
    model?: string | null;
    sourceTaskId?: string | null;
    theme?: FlowchartDiagramTheme | null;
  };
  mermaidCompilation: MermaidCompilation;
}

export interface SaveFlowchartDocumentRequest {
  version: number;
  title: string;
  direction: FlowchartDirection;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export interface FlowchartDocumentSaveResult {
  documentId: string;
  version: number;
  mermaidSource: string;
  mermaidCompilation: MermaidCompilation;
  latestDocument?: FlowchartDocument | null;
}

export interface FlowchartDocumentHistoryItem {
  id: string;
  title: string;
  direction: FlowchartDirection;
  createdAt: string;
  updatedAt: string;
}

export interface FlowchartDocumentHistoryPage {
  records: FlowchartDocumentHistoryItem[];
  offset: number;
  limit: number;
  hasMore: boolean;
}

export interface FlowchartDocumentDeleteResult {
  documentId: string;
}

export interface FlowchartDocumentExportResult {
  taskId: string;
  status: FlowchartTaskStatus;
}

export type FlowchartExportFormat = 'SVG' | 'PNG' | 'MERMAID' | 'JSON';

export async function getFlowchartDocument(documentId: string) {
  return request<FlowchartResult<FlowchartDocument>>(
    '/api/flowchart/documents/get',
    {
      method: 'GET',
      params: { documentId },
    },
  );
}

export async function listFlowchartDocuments(offset = 0, limit = 20) {
  return request<FlowchartResult<FlowchartDocumentHistoryPage>>(
    '/api/flowchart/documents/list',
    {
      method: 'GET',
      params: { offset, limit },
    },
  );
}

export async function saveFlowchartDocument(
  documentId: string,
  payload: SaveFlowchartDocumentRequest,
) {
  return request<FlowchartResult<FlowchartDocumentSaveResult>>(
    '/api/flowchart/documents/save',
    {
      method: 'POST',
      params: { documentId },
      data: payload,
    },
  );
}

export async function deleteFlowchartDocument(documentId: string) {
  return request<FlowchartResult<FlowchartDocumentDeleteResult>>(
    '/api/flowchart/documents/delete',
    {
      method: 'POST',
      params: { documentId },
    },
  );
}

export async function createFlowchartDocumentExport(
  documentId: string,
  format: FlowchartExportFormat,
  background: 'transparent' | 'white' = 'transparent',
) {
  return request<FlowchartResult<FlowchartDocumentExportResult>>(
    '/api/flowchart/documents/export',
    {
      method: 'POST',
      params: { documentId },
      data: { format, background },
    },
  );
}

export async function downloadFlowchartFile(fileId: string) {
  let token: string | null = null;
  try {
    token = window.localStorage.getItem('token');
  } catch {
    token = null;
  }
  const response = await fetch(
    `/api/flowchart/files/download?fileId=${encodeURIComponent(fileId)}`,
    {
      headers: {
        ...(token
          ? { Authorization: `Bearer ${token}` }
          : { 'X-Flowchart-User-Id': 'local-user' }),
      },
    },
  );
  const disposition = response.headers.get('content-disposition') || '';
  const isAttachment = /^attachment(?:;|$)/i.test(disposition.trim());

  // JSON 导出文件与统一业务错误响应都会使用 application/json。下载接口
  // 为成功响应显式设置 attachment，因此必须以该头判断文件，而非 MIME。
  if (!response.ok || !isAttachment) {
    let errorMessage = '导出文件下载失败';
    if (
      (response.headers.get('content-type') || '').includes('application/json')
    ) {
      try {
        const payload = (await response.json()) as {
          message?: string;
          errorCode?: string;
        };
        errorMessage = payload.message || errorMessage;
      } catch {
        // 非法错误响应仍使用通用下载提示。
      }
    }
    throw new Error(errorMessage);
  }
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const filename = encodedName
    ? decodeURIComponent(encodedName)
    : 'flowchart-export';
  return { blob: await response.blob(), filename };
}
