import { history } from '@umijs/max';
import { Button, Result } from 'antd';
import styles from './index.less';

export default function Page404() {
  return (
    <div className={styles.container}>
      <Result
        status="404"
        title="404"
        subTitle="抱歉，您访问的页面不存在"
        extra={
          <Button type="primary" size="large" onClick={() => history.push('/')}>
            返回首页
          </Button>
        }
      />
    </div>
  );
}
