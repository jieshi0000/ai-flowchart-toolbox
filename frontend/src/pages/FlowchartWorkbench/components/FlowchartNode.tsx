import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { CSSProperties } from 'react';
import styles from './diagram.less';
import type { FlowchartCanvasNode } from './diagramFlow';

export function FlowchartNode({
  data,
  selected,
}: NodeProps<FlowchartCanvasNode>) {
  const targetPosition = data.direction === 'LR' ? Position.Left : Position.Top;
  const sourcePosition =
    data.direction === 'LR' ? Position.Right : Position.Bottom;
  const style = {
    '--node-fill': data.fill || '#ffffff',
    '--node-stroke': data.stroke || '#397f78',
  } as CSSProperties;

  return (
    <div
      className={`${styles.nodeFrame} ${selected ? styles.nodeSelected : ''}`}
      aria-label={`${data.label}，${data.nodeType}`}
    >
      <Handle
        className={styles.handle}
        type="target"
        position={targetPosition}
        id="target"
      />
      <div
        className={`${styles.nodeShell} ${styles[data.nodeType]}`}
        style={style}
      >
        <span className={styles.nodeTypeLabel}>{data.nodeType}</span>
        <span className={styles.nodeLabel}>{data.label}</span>
      </div>
      <Handle
        className={styles.handle}
        type="source"
        position={sourcePosition}
        id="source"
      />
    </div>
  );
}
