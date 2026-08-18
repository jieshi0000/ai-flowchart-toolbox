import { request } from '@umijs/max';

export type FlowchartTaskStatus =
  | 'waiting'
  | 'submitting'
  | 'provider_queued'
  | 'provider_processing'
  | 'validating'
  | 'rendering'
  | 'success'
  | 'failed'
  | 'canceled'
  | 'expired';

export interface FlowchartTask {
  taskId: string;
  type?: 'diagram_generate' | 'diagram_export';
  status: FlowchartTaskStatus;
  progress: number;
  stage?: string | null;
  providerId?: string | null;
  modelName?: string | null;
  pollCount?: number;
  documentId?: string | null;
  downloadUrl?: string | null;
  errorCode?: string | null;
  errorMessage?: string | null;
}

export interface FlowchartResult<T> {
  code?: number;
  data?: T | null;
  message?: string;
  errorMessage?: string | null;
  errorCode?: string | number | null;
  success?: boolean;
  timestamp?: number;
}

export interface CreateFlowchartTaskRequest {
  type: 'diagram_generate';
  prompt: string;
  direction: 'TB' | 'LR';
  detailLevel: 'concise' | 'standard' | 'detailed';
  providerId: string | null;
  model: string | null;
  sessionId: string;
  idempotencyKey: string;
}

export interface FlowchartTaskCreateResult {
  taskId: string;
  status: FlowchartTaskStatus;
  estimatedSeconds?: number | null;
}

export interface FlowchartTaskCancelResult {
  taskId: string;
  status: 'canceled';
  providerCancelRequested: boolean;
}

export interface FlowchartTaskRetryResult {
  taskId: string;
  sourceTaskId: string;
  status: FlowchartTaskStatus;
}

export async function getFlowchartTask(taskId: string) {
  return request<FlowchartResult<FlowchartTask>>('/api/flowchart/tasks/get', {
    method: 'GET',
    params: { taskId },
  });
}

export async function listRecoverableFlowchartTasks(sessionId?: string) {
  return request<FlowchartResult<FlowchartTask[]>>(
    '/api/flowchart/tasks/list',
    {
      method: 'GET',
      params: {
        ...(sessionId ? { sessionId } : {}),
        limit: 1,
      },
    },
  );
}

export async function createFlowchartTask(payload: CreateFlowchartTaskRequest) {
  return request<FlowchartResult<FlowchartTaskCreateResult>>(
    '/api/flowchart/tasks/create',
    {
      method: 'POST',
      data: payload,
    },
  );
}

export async function cancelFlowchartTask(taskId: string) {
  return request<FlowchartResult<FlowchartTaskCancelResult>>(
    '/api/flowchart/tasks/cancel',
    {
      method: 'POST',
      params: { taskId },
    },
  );
}

export async function retryFlowchartTask(taskId: string) {
  return request<FlowchartResult<FlowchartTaskRetryResult>>(
    '/api/flowchart/tasks/retry',
    {
      method: 'POST',
      params: { taskId },
    },
  );
}
