import { ApartmentOutlined } from '@ant-design/icons';
import { Empty, Typography } from 'antd';
import { useLeaveConfirmation } from '@/hooks/useLeaveConfirmation';
import {
  isTerminalTaskStatus,
  useTaskMonitor,
} from '@/hooks/useTaskMonitor';
import { restoreTaskContext } from '@/services/flowchart/taskStorage';
import styles from './index.less';

const FlowchartWorkbench: React.FC = () => {
  const { taskId } = restoreTaskContext();
  const { task, connectionMode } = useTaskMonitor({ taskId });
  const hasRunningTask = Boolean(taskId) && (!task || !isTerminalTaskStatus(task.status));

  useLeaveConfirmation({ hasRunningTask });

  return (
    <main className={styles.workbench} data-task-connection={connectionMode}>
      <section className={styles.emptyState} aria-label="流程图工作台">
        <ApartmentOutlined className={styles.icon} />
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Typography.Text type="secondary">
              流程图工作台已准备就绪
            </Typography.Text>
          }
        />
      </section>
    </main>
  );
};

export default FlowchartWorkbench;
