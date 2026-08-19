import type { MermaidPreviewStatus } from '@/models/flowchart';
import { CopyOutlined, FileTextOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Spin, Typography, message } from 'antd';
import styles from './diagram.less';

interface MermaidPanelProps {
  source: string | null;
  status: MermaidPreviewStatus;
  error: string | null;
}

async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Continue with the hidden textarea fallback below.
  }

  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  return copied;
}

export function MermaidPanel({ source, status, error }: MermaidPanelProps) {
  const hasSource = Boolean(source);

  const handleCopy = async () => {
    if (!source) {
      return;
    }
    if (await copyText(source)) {
      message.success('Mermaid 源码已复制');
    } else {
      message.warning('复制失败，请在源码框中手动复制');
    }
  };

  return (
    <section className={styles.mermaidPanel} aria-label="Mermaid 只读预览">
      <div className={styles.propertySectionHeader}>
        <Typography.Text strong>Mermaid 源码</Typography.Text>
        {hasSource ? (
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => void handleCopy()}
          >
            复制
          </Button>
        ) : null}
      </div>
      {status === 'compiling' ? (
        <div className={styles.mermaidState}>
          <Spin size="small" />
          <Typography.Text type="secondary">
            后端正在编译 Mermaid{hasSource ? '，当前保留上一次成功的源码' : ''}
          </Typography.Text>
        </div>
      ) : status === 'failed' ? (
        <Alert
          type="error"
          showIcon
          message="Mermaid 编译失败"
          description={error || '请稍后重试，流程图数据仍可继续编辑。'}
        />
      ) : null}
      {hasSource ? (
        <Input.TextArea
          className={styles.mermaidSource}
          value={source || ''}
          readOnly
          autoSize={{ minRows: 10, maxRows: 22 }}
          aria-label="Mermaid 源码，只读"
        />
      ) : status === 'idle' || status === 'ready' ? (
        <Empty
          image={<FileTextOutlined />}
          imageStyle={{ height: 34, color: '#72908a' }}
          description={
            <Typography.Text type="secondary">
              暂无后端 Mermaid 编译结果
            </Typography.Text>
          }
        />
      ) : null}
      <Typography.Text className={styles.mermaidHint} type="secondary">
        预览只展示后端最近一次成功编译结果，不会反向修改画布。
      </Typography.Text>
    </section>
  );
}
