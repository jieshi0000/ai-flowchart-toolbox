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
  format: 'MERMAID' | 'JSON',
) {
  return request<FlowchartResult<FlowchartDocumentExportResult>>(
    '/api/flowchart/documents/export',
    {
      method: 'POST',
      params: { documentId },
      data: { format, background: 'transparent' },
    },
  );
}
