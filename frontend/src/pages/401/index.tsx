import { history } from '@umijs/max';
import { Button, Result } from 'antd';
import styles from './index.less';

export default function Page401() {
  return (
    <div className={styles.container}>
      <Result
        status="error"
        title="401"
        subTitle="抱歉，您没有权限访问此页面。请重新登录。"
        extra={
          <Button
            type="primary"
            size="large"
            onClick={() => {
              localStorage.removeItem('token');
              history.push('/login');
            }}
          >
            重新登录
          </Button>
        }
      />
    </div>
  );
}
