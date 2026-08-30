import type {
  DiagramData,
  DiagramNode,
  FlowchartNodeType,
} from '@/models/flowchart';
import {
  AlignLeftOutlined,
  ClearOutlined,
  NodeIndexOutlined,
  PlusOutlined,
  RedoOutlined,
  UndoOutlined,
  ZoomInOutlined,
} from '@ant-design/icons';
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
  type Connection,
  type NodeMouseHandler,
  type OnNodeDrag,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Button, Dropdown, Tooltip, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import styles from './diagram.less';
import {
  clampPosition,
  createUniqueEdgeId,
  createUniqueNodeId,
  defaultNodeLabel,
  fromFlowEdges,
  layoutDiagramData,
  toFlowEdges,
  toFlowNodes,
  type FlowchartCanvasEdge,
  type FlowchartCanvasNode,
} from './diagramFlow';
import { FlowchartNode } from './FlowchartNode';

export interface DiagramCanvasProps {
  diagramData: DiagramData;
  selectedElement: { type: 'node' | 'edge'; id: string } | null;
  onChange: (
    next: DiagramData | ((current: DiagramData) => DiagramData),
  ) => void;
  onSelectElement: (
    selectedElement: { type: 'node' | 'edge'; id: string } | null,
  ) => void;
  onReset: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  theme?: 'blue' | 'purple' | 'green';
}

const NODE_TYPE_ORDER: FlowchartNodeType[] = [
  'start',
  'end',
  'process',
  'decision',
  'input_output',
  'subprocess',
];

const NODE_STYLE_BY_TYPE: Record<
  FlowchartNodeType,
  { fill: string; stroke: string }
> = {
  start: { fill: '#e8f4f1', stroke: '#1f8075' },
  end: { fill: '#edf3f5', stroke: '#52717a' },
  process: { fill: '#ffffff', stroke: '#397f78' },
  decision: { fill: '#fff8e7', stroke: '#b07813' },
  input_output: { fill: '#eef7fb', stroke: '#31728c' },
  subprocess: { fill: '#f1effb', stroke: '#6755a0' },
};

const NEW_NODE_COLUMN_COUNT = 4;
const NEW_NODE_HORIZONTAL_GAP = 220;
const NEW_NODE_VERTICAL_GAP = 120;

const nodeTypes = { flowchart: FlowchartNode };

function DiagramCanvasInner({
  diagramData,
  selectedElement,
  onChange,
  onSelectElement,
  onReset,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  theme = 'blue',
}: DiagramCanvasProps) {
  const flowContainerRef = useRef<HTMLDivElement>(null);
  const fitAfterLayoutRef = useRef(false);
  const didInitialFitRef = useRef(false);
  const { fitView, screenToFlowPosition } = useReactFlow<
    FlowchartCanvasNode,
    FlowchartCanvasEdge
  >();
  const initialNodes = useMemo(
    () => toFlowNodes(diagramData.nodes, diagramData.direction),
    // The hook initializer only needs the first render; external changes are
    // synchronized below after the store publishes a new diagram snapshot.
    [],
  );
  const initialEdges = useMemo(() => toFlowEdges(diagramData.edges), []);
  const [nodes, setNodes, onNodesChange] =
    useNodesState<FlowchartCanvasNode>(initialNodes);
  const [edges, setEdges, onEdgesChange] =
    useEdgesState<FlowchartCanvasEdge>(initialEdges);
  const nodesInitialized = useNodesInitialized();
  const diagramSignature = useMemo(
    () => JSON.stringify(diagramData),
    [diagramData],
  );
  const localNodePositionSignature = useMemo(
    () =>
      nodes
        .map((node) => `${node.id}:${node.position.x}:${node.position.y}`)
        .join('|'),
    [nodes],
  );
  const lastDiagramSignatureRef = useRef(diagramSignature);
  const lastDocumentIdRef = useRef(diagramData.id ?? null);

  useEffect(() => {
    if (lastDiagramSignatureRef.current === diagramSignature) {
      return;
    }
    const nextDocumentId = diagramData.id ?? null;
    if (lastDocumentIdRef.current !== nextDocumentId) {
      // 新生成或切换的文档会先经过 dagre 布局；同步节点后重新适应视图，
      // 防止首次结果仍停留在旧画布中心或被工具栏遮挡。
      fitAfterLayoutRef.current = true;
    }
    lastDocumentIdRef.current = nextDocumentId;
    lastDiagramSignatureRef.current = diagramSignature;
    setNodes(toFlowNodes(diagramData.nodes, diagramData.direction));
    setEdges(toFlowEdges(diagramData.edges));
  }, [diagramData, diagramSignature, setEdges, setNodes]);

  useEffect(() => {
    if (!nodesInitialized || !nodes.length) {
      return;
    }
    if (fitAfterLayoutRef.current || !didInitialFitRef.current) {
      fitAfterLayoutRef.current = false;
      didInitialFitRef.current = true;
      window.requestAnimationFrame(() => {
        void fitView({ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 });
      });
    }
  }, [fitView, localNodePositionSignature, nodes.length, nodesInitialized]);

  const nodeMenuItems = NODE_TYPE_ORDER.map((type) => ({
    key: type,
    label: defaultNodeLabel(type),
  }));

  const handleAddNode = useCallback(
    (type: FlowchartNodeType) => {
      if (diagramData.nodes.length >= 50) {
        return;
      }
      const bounds = flowContainerRef.current?.getBoundingClientRect();
      const center = bounds
        ? screenToFlowPosition({
            x: bounds.left + bounds.width / 2,
            y: bounds.top + bounds.height / 2,
          })
        : {
            x: diagramData.nodes.length * 28,
            y: diagramData.nodes.length * 28,
          };
      const nodeIndex = diagramData.nodes.length;
      const gridOffset = {
        x: (nodeIndex % NEW_NODE_COLUMN_COUNT) * NEW_NODE_HORIZONTAL_GAP,
        y:
          Math.floor(nodeIndex / NEW_NODE_COLUMN_COUNT) * NEW_NODE_VERTICAL_GAP,
      };
      const style = NODE_STYLE_BY_TYPE[type];
      const themeColors = theme === 'purple'
        ? { fill: '#f5f1ff', stroke: '#d3c7ff' }
        : theme === 'green'
          ? { fill: '#edfbf5', stroke: '#b5e3d0' }
          : { fill: '#eef5ff', stroke: '#b9d2ff' };
      const nextNode: DiagramNode = {
        id: createUniqueNodeId(diagramData.nodes),
        type,
        label: defaultNodeLabel(type),
        position: clampPosition({
          x: center.x + gridOffset.x,
          y: center.y + gridOffset.y,
        }),
        style: { ...style, ...themeColors },
      };
      onChange((current) => ({
        ...current,
        nodes: [...current.nodes, nextNode],
      }));
      onSelectElement({ type: 'node', id: nextNode.id });
    },
    [diagramData.nodes, onChange, onSelectElement, screenToFlowPosition, theme],
  );

  const handleNodeDragStop = useCallback<OnNodeDrag<FlowchartCanvasNode>>(
    (_event, node) => {
      const position = clampPosition(node.position);
      setNodes((current) =>
        current.map((item) =>
          item.id === node.id ? { ...item, position } : item,
        ),
      );
      onChange((current) => ({
        ...current,
        nodes: current.nodes.map((item) =>
          item.id === node.id ? { ...item, position } : item,
        ),
      }));
    },
    [onChange, setNodes],
  );

  const handleNodesDelete = useCallback(
    (deletedNodes: FlowchartCanvasNode[]) => {
      const deletedIds = new Set(deletedNodes.map((node) => node.id));
      onChange((current) => ({
        ...current,
        nodes: current.nodes.filter((node) => !deletedIds.has(node.id)),
        edges: current.edges.filter(
          (edge) =>
            !deletedIds.has(edge.source) && !deletedIds.has(edge.target),
        ),
      }));
      if (
        selectedElement &&
        selectedElement.type === 'node' &&
        deletedIds.has(selectedElement.id)
      ) {
        onSelectElement(null);
      }
    },
    [onChange, onSelectElement, selectedElement],
  );

  const handleEdgesDelete = useCallback(
    (deletedEdges: FlowchartCanvasEdge[]) => {
      const deletedIds = new Set(deletedEdges.map((edge) => edge.id));
      onChange((current) => ({
        ...current,
        edges: current.edges.filter((edge) => !deletedIds.has(edge.id)),
      }));
      if (
        selectedElement &&
        selectedElement.type === 'edge' &&
        deletedIds.has(selectedElement.id)
      ) {
        onSelectElement(null);
      }
    },
    [onChange, onSelectElement, selectedElement],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (
        !connection.source ||
        !connection.target ||
        diagramData.edges.length >= 100 ||
        !diagramData.nodes.some((node) => node.id === connection.source) ||
        !diagramData.nodes.some((node) => node.id === connection.target)
      ) {
        return;
      }
      const nextEdge: FlowchartCanvasEdge = {
        id: createUniqueEdgeId(diagramData.edges),
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle,
        targetHandle: connection.targetHandle,
        type: 'smoothstep',
        markerEnd: { type: 'arrowclosed' },
      };
      const nextEdges = addEdge(nextEdge, edges);
      setEdges(nextEdges);
      onChange((current) => ({
        ...current,
        edges: fromFlowEdges(nextEdges),
      }));
      onSelectElement({ type: 'edge', id: nextEdge.id });
    },
    [
      diagramData.edges,
      diagramData.nodes,
      edges,
      onChange,
      onSelectElement,
      setEdges,
    ],
  );

  const handleLayout = useCallback(() => {
    const layouted = layoutDiagramData(diagramData);
    fitAfterLayoutRef.current = true;
    setNodes(toFlowNodes(layouted.nodes, layouted.direction));
    setEdges(toFlowEdges(layouted.edges));
    onChange(layouted);
  }, [diagramData, onChange, setEdges, setNodes]);

  const handleNodeClick: NodeMouseHandler<FlowchartCanvasNode> = useCallback(
    (_event, node) => {
      onSelectElement({ type: 'node', id: node.id });
    },
    [onSelectElement],
  );

  const handleEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: FlowchartCanvasEdge) => {
      onSelectElement({ type: 'edge', id: edge.id });
    },
    [onSelectElement],
  );

  const handlePaneClick = useCallback(() => {
    onSelectElement(null);
  }, [onSelectElement]);

  const handleFitView = useCallback(() => {
    void fitView({ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 });
  }, [fitView]);

  return (
    <div ref={flowContainerRef} className={styles.diagramCanvas}>
      <div className={styles.canvasToolbar} aria-label="画布工具">
        <Dropdown
          trigger={['click']}
          menu={{
            items: nodeMenuItems,
            onClick: ({ key }) => handleAddNode(key as FlowchartNodeType),
          }}
          disabled={diagramData.nodes.length >= 50}
        >
          <Button size="small" type="primary" icon={<PlusOutlined />}>
            新增节点
          </Button>
        </Dropdown>
        <Tooltip title="自动布局">
          <Button
            aria-label="自动布局"
            size="small"
            icon={<AlignLeftOutlined />}
            onClick={handleLayout}
          />
        </Tooltip>
        <Tooltip title="适应视图">
          <Button
            aria-label="适应视图"
            size="small"
            icon={<ZoomInOutlined />}
            onClick={handleFitView}
          />
        </Tooltip>
        <Tooltip title="撤销">
          <Button
            aria-label="撤销"
            size="small"
            icon={<UndoOutlined />}
            disabled={!canUndo}
            onClick={onUndo}
          />
        </Tooltip>
        <Tooltip title="重做">
          <Button
            aria-label="重做"
            size="small"
            icon={<RedoOutlined />}
            disabled={!canRedo}
            onClick={onRedo}
          />
        </Tooltip>
        <Tooltip title="清空画布">
          <Button
            aria-label="清空画布"
            size="small"
            danger
            icon={<ClearOutlined />}
            disabled={!diagramData.nodes.length && !diagramData.edges.length}
            onClick={onReset}
          />
        </Tooltip>
        <span className={styles.canvasToolbarLabel}>
          {diagramData.nodes.length}/50 节点 · {diagramData.edges.length}/100
          连线
        </span>
      </div>

      <ReactFlow<FlowchartCanvasNode, FlowchartCanvasEdge>
        className={styles.reactFlow}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodesDelete={handleNodesDelete}
        onEdgesDelete={handleEdgesDelete}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        onNodeDragStop={handleNodeDragStop}
        onConnect={handleConnect}
        minZoom={0.5}
        maxZoom={1.5}
        deleteKeyCode="Delete"
        nodesConnectable
        nodesDraggable
        elementsSelectable
        fitView={false}
        defaultEdgeOptions={{
          type: 'smoothstep',
          markerEnd: { type: 'arrowclosed' },
        }}
        aria-label="流程图编辑画布"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1}
          color="#d5e1f2"
        />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) =>
            (node.data as Partial<FlowchartCanvasNode['data']>)?.stroke ||
            '#397f78'
          }
        />
      </ReactFlow>

      {!nodes.length ? (
        <div className={styles.emptyCanvas}>
          <NodeIndexOutlined aria-hidden="true" />
          <span className={styles.emptyCanvasTitle}>从一个节点开始编辑</span>
          <Typography.Text type="secondary">
            使用“新增节点”添加步骤，再拖动节点上的连接点建立流程。
          </Typography.Text>
          <Button
            size="small"
            icon={<PlusOutlined />}
            onClick={() => handleAddNode('start')}
          >
            添加开始节点
          </Button>
        </div>
      ) : null}
      <div className={styles.canvasHint}>
        双击节点或连线可打开右侧属性；按 Delete 删除选中内容。
      </div>
    </div>
  );
}

export default function DiagramCanvas(props: DiagramCanvasProps) {
  return (
    <ReactFlowProvider>
      <DiagramCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
