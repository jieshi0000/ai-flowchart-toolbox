import {
  clampDiagramCoordinate,
  cloneDiagramData,
  FLOWCHART_NODE_TYPE_LABELS,
  type DiagramData,
  type DiagramEdge,
  type DiagramNode,
  type FlowchartNodeType,
} from '@/models/flowchart';
import type { FlowchartDirection } from '@/services/flowchart/workbench';
import {
  MarkerType,
  type Edge,
  type Node,
  type XYPosition,
} from '@xyflow/react';
import dagre from 'dagre';

export interface FlowchartNodeData extends Record<string, unknown> {
  label: string;
  nodeType: FlowchartNodeType;
  direction: FlowchartDirection;
  fill?: string;
  stroke?: string;
}

export type FlowchartCanvasNode = Node<FlowchartNodeData, 'flowchart'>;

export interface FlowchartEdgeData extends Record<string, unknown> {
  condition?: string;
}

export type FlowchartCanvasEdge = Edge<FlowchartEdgeData>;

export const NODE_DEFAULT_LABELS: Record<FlowchartNodeType, string> = {
  start: '开始',
  end: '结束',
  process: '处理步骤',
  decision: '判断条件',
  input_output: '输入或输出',
  subprocess: '子流程',
};

export function toFlowNodes(
  nodes: DiagramNode[],
  direction: FlowchartDirection,
): FlowchartCanvasNode[] {
  return nodes.map((node) => ({
    id: node.id,
    type: 'flowchart',
    position: {
      x: clampDiagramCoordinate(node.position.x),
      y: clampDiagramCoordinate(node.position.y),
    },
    data: {
      label: node.label,
      nodeType: node.type,
      direction,
      fill: node.style?.fill,
      stroke: node.style?.stroke,
    },
  }));
}

export function toFlowEdges(edges: DiagramEdge[]): FlowchartCanvasEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    label: edge.label || edge.condition || undefined,
    data: edge.condition ? { condition: edge.condition } : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
}

export function fromFlowNodes(nodes: FlowchartCanvasNode[]): DiagramNode[] {
  return nodes.map((node) => ({
    id: node.id,
    type: node.data.nodeType,
    label: node.data.label.trim() || NODE_DEFAULT_LABELS[node.data.nodeType],
    position: {
      x: clampDiagramCoordinate(node.position.x),
      y: clampDiagramCoordinate(node.position.y),
    },
    ...(node.data.fill || node.data.stroke
      ? {
          style: {
            ...(node.data.fill ? { fill: node.data.fill } : {}),
            ...(node.data.stroke ? { stroke: node.data.stroke } : {}),
          },
        }
      : {}),
  }));
}

export function fromFlowEdges(edges: FlowchartCanvasEdge[]): DiagramEdge[] {
  return edges.map((edge) => {
    const label = typeof edge.label === 'string' ? edge.label.trim() : '';
    const condition =
      typeof edge.data?.condition === 'string'
        ? edge.data.condition.trim()
        : '';
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...(label ? { label } : {}),
      ...(condition ? { condition } : {}),
    };
  });
}

export function createUniqueNodeId(nodes: DiagramNode[]): string {
  const existing = new Set(nodes.map((node) => node.id));
  let index = nodes.length + 1;
  let candidate = `node-${index}`;
  while (existing.has(candidate)) {
    index += 1;
    candidate = `node-${index}`;
  }
  return candidate;
}

export function createUniqueEdgeId(edges: DiagramEdge[]): string {
  const existing = new Set(edges.map((edge) => edge.id));
  let index = edges.length + 1;
  let candidate = `edge-${index}`;
  while (existing.has(candidate)) {
    index += 1;
    candidate = `edge-${index}`;
  }
  return candidate;
}

export function defaultNodeLabel(type: FlowchartNodeType): string {
  return NODE_DEFAULT_LABELS[type] || FLOWCHART_NODE_TYPE_LABELS[type];
}

export function clampPosition(position: XYPosition): XYPosition {
  return {
    x: clampDiagramCoordinate(position.x),
    y: clampDiagramCoordinate(position.y),
  };
}

const LAYOUT_NODE_WIDTH = 180;
const LAYOUT_NODE_HEIGHT = 68;

export function layoutDiagramData(data: DiagramData): DiagramData {
  if (!data.nodes.length) {
    return cloneDiagramData(data);
  }

  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: data.direction,
    nodesep: 64,
    ranksep: 92,
    marginx: 24,
    marginy: 24,
  });

  for (const node of data.nodes) {
    graph.setNode(node.id, {
      width: LAYOUT_NODE_WIDTH,
      height: LAYOUT_NODE_HEIGHT,
    });
  }
  for (const edge of data.edges) {
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);
  const next = cloneDiagramData(data);
  next.nodes = next.nodes.map((node) => {
    const position = graph.node(node.id);
    if (!position) {
      return node;
    }
    return {
      ...node,
      position: clampPosition({
        x: position.x - LAYOUT_NODE_WIDTH / 2,
        y: position.y - LAYOUT_NODE_HEIGHT / 2,
      }),
    };
  });
  return next;
}
