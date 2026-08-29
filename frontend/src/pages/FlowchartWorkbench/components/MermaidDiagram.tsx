import type { MermaidPreviewStatus } from '@/models/flowchart';
import { Alert, Empty, Spin, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import styles from './diagram.less';

interface MermaidDiagramProps {
  source: string | null;
  status: MermaidPreviewStatus;
  error: string | null;
  theme?: 'blue' | 'purple' | 'green';
}

let renderSequence = 0;
let mermaidModulePromise: ReturnType<typeof loadMermaidModule> | null = null;

const MERMAID_THEME_VARIABLES: Record<
  'blue' | 'purple' | 'green',
  Record<string, string>
> = {
  blue: {
    primaryColor: '#EEF5FF',
    primaryBorderColor: '#8EB8FF',
    primaryTextColor: '#24549E',
    lineColor: '#7A8CA8',
    secondaryColor: '#EEF7FB',
    tertiaryColor: '#F3F0FF',
  },
  purple: {
    primaryColor: '#F5F1FF',
    primaryBorderColor: '#B7A8F0',
    primaryTextColor: '#5B4A9B',
    lineColor: '#8175A8',
    secondaryColor: '#F1F4FF',
    tertiaryColor: '#F7EFFF',
  },
  green: {
    primaryColor: '#EDFBF5',
    primaryBorderColor: '#8ED3B6',
    primaryTextColor: '#27765D',
    lineColor: '#6D9C8A',
    secondaryColor: '#EEFAF8',
    tertiaryColor: '#F0F8F4',
  },
};

async function loadMermaidModule() {
  const { default: mermaid } = await import('mermaid');
  return mermaid;
}

function getMermaidModule() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = loadMermaidModule();
  }
  return mermaidModulePromise;
}

export function MermaidDiagram({
  source,
  status,
  error,
  theme = 'blue',
}: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
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

    const renderId = `flowchart-mermaid-${++renderSequence}`;
    void getMermaidModule()
      .then((mermaid) => {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'base',
          themeVariables: MERMAID_THEME_VARIABLES[theme],
          flowchart: {
            htmlLabels: false,
            useMaxWidth: true,
            curve: 'basis',
          },
        });
        return mermaid.render(renderId, source);
      })
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
  }, [source, theme]);

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
