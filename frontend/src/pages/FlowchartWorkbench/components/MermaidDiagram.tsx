import type { MermaidPreviewStatus } from '@/models/flowchart';
import { Alert, Empty, Spin, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import styles from './diagram.less';

interface MermaidDiagramProps {
  source: string | null;
  status: MermaidPreviewStatus;
  error: string | null;
}

let renderSequence = 0;
let mermaidModulePromise: ReturnType<typeof loadMermaidModule> | null = null;

async function loadMermaidModule() {
  const { default: mermaid } = await import('mermaid');
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    flowchart: {
      htmlLabels: false,
      useMaxWidth: true,
      curve: 'basis',
    },
  });
  return mermaid;
}

function getMermaidModule() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = loadMermaidModule();
  }
  return mermaidModulePromise;
}

export function MermaidDiagram({ source, status, error }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const renderIdRef = useRef(`flowchart-mermaid-${++renderSequence}`);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    const container = containerRef.current;
    if (container) {
      container.replaceChildren();
    }
    setRenderError(null);
    if (!source?.trim()) {
      return () => {
        disposed = true;
      };
    }

    void getMermaidModule()
      .then((mermaid) => mermaid.render(renderIdRef.current, source))
      .then(({ svg }) => {
        if (disposed || !containerRef.current) {
          return;
        }
        // 源码已在后端按受限 Mermaid 规则校验，且 Mermaid 使用 strict 模式。
        // render() 返回 SVG 字符串，必须在此处挂载到预览容器。
        containerRef.current.innerHTML = svg;
      })
      .catch(() => {
        if (!disposed) {
          setRenderError('流程图预览渲染失败，可在 Mermaid 面板查看源码。');
        }
      });

    return () => {
      disposed = true;
    };
  }, [source]);

  if (!source?.trim()) {
    return (
      <div className={styles.mermaidDiagramState} aria-live="polite">
        {status === 'compiling' ? <Spin size="small" /> : null}
        <Typography.Text type="secondary">
          {status === 'compiling'
            ? '正在准备 Mermaid 流程图'
            : '暂无可展示的 Mermaid 流程图'}
        </Typography.Text>
      </div>
    );
  }

  return (
    <section className={styles.mermaidDiagramPreview} aria-label="AI 流程图预览">
      <div
        ref={containerRef}
        className={styles.mermaidSvgViewport}
        data-testid="mermaid-rendered-diagram"
        aria-label="Mermaid 渲染流程图"
      />
      {status === 'compiling' ? (
        <Typography.Text type="secondary">
          后端正在更新 Mermaid，当前展示上一次成功结果。
        </Typography.Text>
      ) : null}
      {status === 'failed' || renderError ? (
        <Alert
          type="error"
          showIcon
          message="Mermaid 渲染失败"
          description={error || renderError || '请在编辑器中继续处理流程图数据。'}
        />
      ) : null}
    </section>
  );
}
