import { request } from '@umijs/max';
import type { FlowchartResult } from './task';

export type FlowchartDirection = 'TB' | 'LR';
export type FlowchartDetailLevel = 'concise' | 'standard' | 'detailed';
export type FlowchartDiagramTheme = 'blue' | 'purple' | 'green';
export type ProviderStatus =
  | 'healthy'
  | 'unhealthy'
  | 'rate_limited'
  | 'disabled';

export interface FlowchartProvider {
  providerId: string;
  displayName: string;
  model: string;
  capabilities: string[];
  status: ProviderStatus;
  allowManualSelection: boolean;
}

export interface FlowchartTemplate {
  id: string;
  category: string;
  name: string;
  description: string;
  direction: FlowchartDirection;
}

export async function getFlowchartProviders() {
  return request<FlowchartResult<FlowchartProvider[]>>(
    '/api/flowchart/providers/list',
    {
      method: 'GET',
    },
  );
}

export async function getFlowchartTemplates() {
  return request<FlowchartResult<FlowchartTemplate[]>>(
    '/api/flowchart/templates/list',
    {
      method: 'GET',
    },
  );
}
