import type { DiagramEdge, DiagramNode } from '@/models/flowchart';
import { request } from '@umijs/max';
import type { FlowchartResult, FlowchartTaskStatus } from './task';
import type { FlowchartDirection } from './workbench';

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
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    },
  );
  if (!response.ok) {
    throw new Error('导出文件下载失败');
  }
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const payload = (await response.json()) as {
      message?: string;
      errorCode?: string;
    };
    throw new Error(payload.message || '导出文件下载失败');
  }
  const disposition = response.headers.get('content-disposition') || '';
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const filename = encodedName
    ? decodeURIComponent(encodedName)
    : 'flowchart-export';
  return { blob: await response.blob(), filename };
}
