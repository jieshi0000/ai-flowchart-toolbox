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

interface Result<T> {
  code: number;
  data?: T | null;
  message?: string;
  timestamp?: number;
}

export async function getFlowchartTask(taskId: string) {
  return request<Result<FlowchartTask>>('/api/flowchart/tasks/get', {
    method: 'GET',
    params: { taskId },
  });
}
