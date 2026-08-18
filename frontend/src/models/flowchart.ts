import type { FlowchartTask } from '@/services/flowchart/task';
import type {
  FlowchartDetailLevel,
  FlowchartDirection,
  FlowchartProvider,
  FlowchartTemplate,
} from '@/services/flowchart/workbench';
import { create } from 'zustand';

export type ProviderLoadState = 'idle' | 'loading' | 'ready' | 'failed';
export type TemplateLoadState = 'idle' | 'loading' | 'ready' | 'failed';

interface FlowchartWorkbenchState {
  prompt: string;
  direction: FlowchartDirection;
  detailLevel: FlowchartDetailLevel;
  selectedModel: string;
  activeTaskId: string | null;
  task: FlowchartTask | null;
  providers: FlowchartProvider[];
  templates: FlowchartTemplate[];
  providerLoadState: ProviderLoadState;
  templateLoadState: TemplateLoadState;
  providerNoticeDismissed: boolean;
  setPrompt: (prompt: string) => void;
  setDirection: (direction: FlowchartDirection) => void;
  setDetailLevel: (detailLevel: FlowchartDetailLevel) => void;
  setSelectedModel: (selectedModel: string) => void;
  setActiveTaskId: (activeTaskId: string | null) => void;
  setTask: (task: FlowchartTask | null) => void;
  setProviders: (providers: FlowchartProvider[]) => void;
  setTemplates: (templates: FlowchartTemplate[]) => void;
  setProviderLoadState: (providerLoadState: ProviderLoadState) => void;
  setTemplateLoadState: (templateLoadState: TemplateLoadState) => void;
  dismissProviderNotice: () => void;
}

export const AUTO_ROUTE_MODEL = '__auto_route__';

export const useFlowchartWorkbenchStore = create<FlowchartWorkbenchState>(
  (set) => ({
    prompt: '',
    direction: 'TB',
    detailLevel: 'standard',
    selectedModel: AUTO_ROUTE_MODEL,
    activeTaskId: null,
    task: null,
    providers: [],
    templates: [],
    providerLoadState: 'idle',
    templateLoadState: 'idle',
    providerNoticeDismissed: false,
    setPrompt: (prompt) => set({ prompt }),
    setDirection: (direction) => set({ direction }),
    setDetailLevel: (detailLevel) => set({ detailLevel }),
    setSelectedModel: (selectedModel) => set({ selectedModel }),
    setActiveTaskId: (activeTaskId) => set({ activeTaskId }),
    setTask: (task) => set({ task }),
    setProviders: (providers) => set({ providers, providerLoadState: 'ready' }),
    setTemplates: (templates) => set({ templates, templateLoadState: 'ready' }),
    setProviderLoadState: (providerLoadState) => set({ providerLoadState }),
    setTemplateLoadState: (templateLoadState) => set({ templateLoadState }),
    dismissProviderNotice: () => set({ providerNoticeDismissed: true }),
  }),
);
