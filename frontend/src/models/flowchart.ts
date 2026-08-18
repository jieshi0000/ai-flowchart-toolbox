import type { FlowchartTask } from '@/services/flowchart/task';
import type {
  FlowchartDetailLevel,
  FlowchartDirection,
  FlowchartProvider,
  FlowchartTemplate,
} from '@/services/flowchart/workbench';
import { temporal } from 'zundo';
import { create } from 'zustand';

export type ProviderLoadState = 'idle' | 'loading' | 'ready' | 'failed';
export type TemplateLoadState = 'idle' | 'loading' | 'ready' | 'failed';

export type FlowchartNodeType =
  | 'start'
  | 'end'
  | 'process'
  | 'decision'
  | 'input_output'
  | 'subprocess';

export interface DiagramNodeStyle {
  fill?: string;
  stroke?: string;
}

export interface DiagramNode {
  id: string;
  type: FlowchartNodeType;
  label: string;
  position: { x: number; y: number };
  style?: DiagramNodeStyle;
}

export interface DiagramEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  condition?: string;
}

export interface DiagramData {
  id?: string | null;
  title: string;
  direction: FlowchartDirection;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export type MermaidPreviewStatus = 'idle' | 'compiling' | 'ready' | 'failed';

export const FLOWCHART_NODE_TYPE_LABELS: Record<FlowchartNodeType, string> = {
  start: '开始',
  end: '结束',
  process: '处理',
  decision: '判断',
  input_output: '输入 / 输出',
  subprocess: '子流程',
};

export const DIAGRAM_POSITION_LIMIT = 10_000;

export function createEmptyDiagramData(
  direction: FlowchartDirection = 'TB',
): DiagramData {
  return {
    title: '未命名流程图',
    direction,
    nodes: [],
    edges: [],
  };
}

export function clampDiagramCoordinate(value: number): number {
  return Math.max(
    -DIAGRAM_POSITION_LIMIT,
    Math.min(DIAGRAM_POSITION_LIMIT, Number.isFinite(value) ? value : 0),
  );
}

export function cloneDiagramData(data: DiagramData): DiagramData {
  return {
    id: data.id ?? null,
    title: data.title,
    direction: data.direction,
    nodes: data.nodes.map((node) => ({
      ...node,
      position: {
        x: clampDiagramCoordinate(node.position.x),
        y: clampDiagramCoordinate(node.position.y),
      },
      ...(node.style ? { style: { ...node.style } } : {}),
    })),
    edges: data.edges.map((edge) => ({ ...edge })),
  };
}

export function areDiagramDataEqual(
  left: DiagramData,
  right: DiagramData,
): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export interface FlowchartWorkbenchState {
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
  diagramData: DiagramData;
  savedDiagramData: DiagramData;
  mermaidSource: string | null;
  mermaidStatus: MermaidPreviewStatus;
  mermaidError: string | null;
  selectedElement: { type: 'node' | 'edge'; id: string } | null;
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
  setDiagramData: (
    diagramData: DiagramData | ((current: DiagramData) => DiagramData),
  ) => void;
  markDiagramSaved: () => void;
  resetDiagram: () => void;
  setMermaidPreview: (payload: {
    source: string | null;
    status: MermaidPreviewStatus;
    error?: string | null;
  }) => void;
  setSelectedElement: (
    selectedElement: { type: 'node' | 'edge'; id: string } | null,
  ) => void;
}

export const AUTO_ROUTE_MODEL = '__auto_route__';

export const useFlowchartWorkbenchStore = create<FlowchartWorkbenchState>()(
  temporal(
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
      diagramData: createEmptyDiagramData(),
      savedDiagramData: createEmptyDiagramData(),
      mermaidSource: null,
      mermaidStatus: 'idle',
      mermaidError: null,
      selectedElement: null,
      setPrompt: (prompt) => set({ prompt }),
      setDirection: (direction) => set({ direction }),
      setDetailLevel: (detailLevel) => set({ detailLevel }),
      setSelectedModel: (selectedModel) => set({ selectedModel }),
      setActiveTaskId: (activeTaskId) => set({ activeTaskId }),
      setTask: (task) => set({ task }),
      setProviders: (providers) =>
        set({ providers, providerLoadState: 'ready' }),
      setTemplates: (templates) =>
        set({ templates, templateLoadState: 'ready' }),
      setProviderLoadState: (providerLoadState) => set({ providerLoadState }),
      setTemplateLoadState: (templateLoadState) => set({ templateLoadState }),
      dismissProviderNotice: () => set({ providerNoticeDismissed: true }),
      setDiagramData: (nextDiagramData) =>
        set((state) => ({
          diagramData: cloneDiagramData(
            typeof nextDiagramData === 'function'
              ? nextDiagramData(state.diagramData)
              : nextDiagramData,
          ),
        })),
      markDiagramSaved: () =>
        set((state) => ({
          savedDiagramData: cloneDiagramData(state.diagramData),
        })),
      resetDiagram: () =>
        set((state) => ({
          diagramData: createEmptyDiagramData(state.diagramData.direction),
          selectedElement: null,
        })),
      setMermaidPreview: ({ source, status, error = null }) =>
        set({
          mermaidSource: source,
          mermaidStatus: status,
          mermaidError: error,
        }),
      setSelectedElement: (selectedElement) => set({ selectedElement }),
    }),
    {
      limit: 30,
      partialize: (state) => ({ diagramData: state.diagramData }),
      equality: (pastState, currentState) =>
        areDiagramDataEqual(pastState.diagramData, currentState.diagramData),
    },
  ),
);

export function isDiagramDirty(state: FlowchartWorkbenchState): boolean {
  return !areDiagramDataEqual(state.diagramData, state.savedDiagramData);
}
