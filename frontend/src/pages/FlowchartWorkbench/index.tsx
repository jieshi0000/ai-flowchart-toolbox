import { ApartmentOutlined } from '@ant-design/icons';
import { Empty, Typography } from 'antd';
import styles from './index.less';

const FlowchartWorkbench: React.FC = () => (
  <main className={styles.workbench}>
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

export default FlowchartWorkbench;
