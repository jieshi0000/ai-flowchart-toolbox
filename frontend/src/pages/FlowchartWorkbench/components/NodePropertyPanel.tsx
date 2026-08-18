import {
  FLOWCHART_NODE_TYPE_LABELS,
  type DiagramData,
  type DiagramNode,
  type FlowchartNodeType,
} from '@/models/flowchart';
import {
  CopyOutlined,
  DeleteOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons';
import {
  Button,
  Empty,
  Input,
  InputNumber,
  Segmented,
  Select,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import styles from './diagram.less';

interface NodePropertyPanelProps {
  diagramData: DiagramData;
  selectedElement: { type: 'node' | 'edge'; id: string } | null;
  onChange: (
    next: DiagramData | ((current: DiagramData) => DiagramData),
  ) => void;
  onSelectElement: (
    selectedElement: { type: 'node' | 'edge'; id: string } | null,
  ) => void;
  onDeleteSelected: () => void;
  onDuplicateNode: (nodeId: string) => void;
}

const nodeTypeOptions = Object.entries(FLOWCHART_NODE_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

function updateNode(
  onChange: NodePropertyPanelProps['onChange'],
  nodeId: string,
  patch: Partial<DiagramNode>,
) {
  onChange((current) => ({
    ...current,
    nodes: current.nodes.map((node) =>
      node.id === nodeId ? { ...node, ...patch } : node,
    ),
  }));
}

export function NodePropertyPanel({
  diagramData,
  selectedElement,
  onChange,
  onSelectElement,
  onDeleteSelected,
  onDuplicateNode,
}: NodePropertyPanelProps) {
  const selectedNode = useMemo(
    () =>
      selectedElement?.type === 'node'
        ? diagramData.nodes.find((node) => node.id === selectedElement.id) ||
          null
        : null,
    [diagramData.nodes, selectedElement],
  );
  const selectedEdge = useMemo(
    () =>
      selectedElement?.type === 'edge'
        ? diagramData.edges.find((edge) => edge.id === selectedElement.id) ||
          null
        : null,
    [diagramData.edges, selectedElement],
  );
  const [titleDraft, setTitleDraft] = useState(diagramData.title);
  const [labelDraft, setLabelDraft] = useState(selectedNode?.label || '');
  const [edgeLabelDraft, setEdgeLabelDraft] = useState(
    selectedEdge?.label || '',
  );
  const [conditionDraft, setConditionDraft] = useState(
    selectedEdge?.condition || '',
  );

  useEffect(() => setTitleDraft(diagramData.title), [diagramData.title]);
  useEffect(
    () => setLabelDraft(selectedNode?.label || ''),
    [selectedNode?.id, selectedNode?.label],
  );
  useEffect(
    () => setEdgeLabelDraft(selectedEdge?.label || ''),
    [selectedEdge?.id, selectedEdge?.label],
  );
  useEffect(
    () => setConditionDraft(selectedEdge?.condition || ''),
    [selectedEdge?.id, selectedEdge?.condition],
  );

  const commitTitle = () => {
    const title = titleDraft.trim();
    if (!title || title === diagramData.title) {
      setTitleDraft(diagramData.title);
      return;
    }
    onChange((current) => ({ ...current, title }));
  };

  const commitNodeLabel = () => {
    if (!selectedNode) {
      return;
    }
    const label = labelDraft.trim() || selectedNode.label;
    setLabelDraft(label);
    if (label !== selectedNode.label) {
      updateNode(onChange, selectedNode.id, { label });
    }
  };

  const commitEdgeText = () => {
    if (!selectedEdge) {
      return;
    }
    const label = edgeLabelDraft.trim();
    const condition = conditionDraft.trim();
    if (
      label !== (selectedEdge.label || '') ||
      condition !== (selectedEdge.condition || '')
    ) {
      onChange((current) => ({
        ...current,
        edges: current.edges.map((edge) =>
          edge.id === selectedEdge.id
            ? {
                ...edge,
                ...(label ? { label } : { label: undefined }),
                ...(condition ? { condition } : { condition: undefined }),
              }
            : edge,
        ),
      }));
    }
  };

  return (
    <div className={styles.propertyPanel}>
      <section className={styles.propertySection} aria-label="文档属性">
        <div className={styles.propertySectionHeader}>
          <Typography.Text strong>文档属性</Typography.Text>
          <Typography.Text type="secondary">本地草稿</Typography.Text>
        </div>
        <label className={styles.propertyLabel} htmlFor="diagram-title">
          标题
        </label>
        <Input
          id="diagram-title"
          value={titleDraft}
          maxLength={100}
          onChange={(event) => setTitleDraft(event.target.value)}
          onBlur={commitTitle}
          onPressEnter={commitTitle}
        />
        <label className={styles.propertyLabel}>布局方向</label>
        <Segmented
          block
          value={diagramData.direction}
          options={[
            { label: '自上而下', value: 'TB' },
            { label: '从左到右', value: 'LR' },
          ]}
          onChange={(value) =>
            onChange((current) => ({
              ...current,
              direction: value as 'TB' | 'LR',
            }))
          }
        />
      </section>

      {selectedNode ? (
        <section className={styles.propertySection} aria-label="节点属性">
          <div className={styles.propertySectionHeader}>
            <Typography.Text strong>节点属性</Typography.Text>
            <Typography.Text type="secondary">
              {selectedNode.id}
            </Typography.Text>
          </div>
          <label className={styles.propertyLabel} htmlFor="node-label">
            节点文本
          </label>
          <Input
            id="node-label"
            value={labelDraft}
            maxLength={120}
            onChange={(event) => setLabelDraft(event.target.value)}
            onBlur={commitNodeLabel}
            onPressEnter={commitNodeLabel}
          />
          <label className={styles.propertyLabel}>节点类型</label>
          <Select
            value={selectedNode.type}
            options={nodeTypeOptions}
            onChange={(value) =>
              updateNode(onChange, selectedNode.id, {
                type: value as FlowchartNodeType,
              })
            }
          />
          <div className={styles.positionGrid}>
            <label className={styles.propertyLabel} htmlFor="node-position-x">
              X 坐标
              <InputNumber
                id="node-position-x"
                value={Math.round(selectedNode.position.x)}
                controls={false}
                onChange={(value) =>
                  typeof value === 'number' &&
                  updateNode(onChange, selectedNode.id, {
                    position: { ...selectedNode.position, x: value },
                  })
                }
              />
            </label>
            <label className={styles.propertyLabel} htmlFor="node-position-y">
              Y 坐标
              <InputNumber
                id="node-position-y"
                value={Math.round(selectedNode.position.y)}
                controls={false}
                onChange={(value) =>
                  typeof value === 'number' &&
                  updateNode(onChange, selectedNode.id, {
                    position: { ...selectedNode.position, y: value },
                  })
                }
              />
            </label>
          </div>
          <div className={styles.colorGrid}>
            <label className={styles.propertyLabel} htmlFor="node-fill">
              填充色
              <input
                id="node-fill"
                className={styles.colorInput}
                type="color"
                value={selectedNode.style?.fill || '#ffffff'}
                onChange={(event) =>
                  updateNode(onChange, selectedNode.id, {
                    style: {
                      ...selectedNode.style,
                      fill: event.target.value.toUpperCase(),
                    },
                  })
                }
              />
            </label>
            <label className={styles.propertyLabel} htmlFor="node-stroke">
              边框色
              <input
                id="node-stroke"
                className={styles.colorInput}
                type="color"
                value={selectedNode.style?.stroke || '#397F78'}
                onChange={(event) =>
                  updateNode(onChange, selectedNode.id, {
                    style: {
                      ...selectedNode.style,
                      stroke: event.target.value.toUpperCase(),
                    },
                  })
                }
              />
            </label>
          </div>
          <div className={styles.propertyActions}>
            <Button
              icon={<CopyOutlined />}
              onClick={() => onDuplicateNode(selectedNode.id)}
            >
              复制节点
            </Button>
            <Button danger icon={<DeleteOutlined />} onClick={onDeleteSelected}>
              删除节点
            </Button>
          </div>
        </section>
      ) : selectedEdge ? (
        <section className={styles.propertySection} aria-label="连线属性">
          <div className={styles.propertySectionHeader}>
            <Typography.Text strong>连线属性</Typography.Text>
            <Typography.Text type="secondary">
              {selectedEdge.id}
            </Typography.Text>
          </div>
          <div className={styles.edgeEndpoints}>
            {selectedEdge.source} <span aria-hidden="true">→</span>{' '}
            {selectedEdge.target}
          </div>
          <label className={styles.propertyLabel} htmlFor="edge-label">
            连线标签
          </label>
          <Input
            id="edge-label"
            value={edgeLabelDraft}
            maxLength={120}
            placeholder="例如：通过"
            onChange={(event) => setEdgeLabelDraft(event.target.value)}
            onBlur={commitEdgeText}
            onPressEnter={commitEdgeText}
          />
          <label className={styles.propertyLabel} htmlFor="edge-condition">
            判断条件
          </label>
          <Input
            id="edge-condition"
            value={conditionDraft}
            maxLength={120}
            placeholder="可选"
            onChange={(event) => setConditionDraft(event.target.value)}
            onBlur={commitEdgeText}
            onPressEnter={commitEdgeText}
          />
          <Button danger icon={<DeleteOutlined />} onClick={onDeleteSelected}>
            删除连线
          </Button>
        </section>
      ) : (
        <div className={styles.propertyEmpty}>
          <Empty
            image={<NodeIndexOutlined />}
            imageStyle={{ height: 32, color: '#72908a' }}
            description="选择节点或连线查看属性"
          />
        </div>
      )}

      {selectedElement ? (
        <Button
          type="link"
          onClick={() => onSelectElement(null)}
          className={styles.clearSelectionButton}
        >
          清除选择
        </Button>
      ) : null}
    </div>
  );
}
