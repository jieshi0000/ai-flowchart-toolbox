import { getCaptcha, login } from '@/services/demo/auth';
import {
  AlipayOutlined,
  LockOutlined,
  MobileOutlined,
  SafetyCertificateOutlined,
  TaobaoOutlined,
  UserOutlined,
  WeiboOutlined,
} from '@ant-design/icons';
import {
  LoginForm,
  ProFormCheckbox,
  ProFormText,
} from '@ant-design/pro-components';
import { history, useModel } from '@umijs/max';
import { Divider, Image, message, Space, Tabs } from 'antd';
import { useEffect, useState } from 'react';
import styles from './index.less';

export default function LoginPage() {
  const [captchaKey, setCaptchaKey] = useState<string>('');
  const [captchaImage, setCaptchaImage] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [loginType, setLoginType] = useState('account');
  const { initialState, setInitialState } = useModel('@@initialState');

  const PROJECT_TITLE = process.env.VITE_APP_TITLE;

  const fetchCaptcha = async () => {
    try {
      const res = await getCaptcha();
      if (res.code === 200) {
        setCaptchaKey(res.data.captchaKey);
        setCaptchaImage(res.data.captchaImage);
      }
    } catch {
      message.error('获取验证码失败');
    }
  };

  useEffect(() => {
    if (initialState?.captchaEnabled) {
      fetchCaptcha();
    }
  }, []);

  const handleSubmit = async (values: any) => {
    setLoading(true);
    try {
      const res = await login({
        username: values.username,
        password: values.password,
        captchaKey,
        captchaCode: values.captcha,
      });
      // 走到这说明请求成功（adaptor 判定 success=true），res.code 一定是 200
      message.success('登录成功');
      localStorage.setItem('token', res.data.token);
      setInitialState((s: any) => ({ ...s, currentUser: res.data }));
      history.push('/');
    } catch {
      // adaptor 判定 success=false 时请求会 reject，错误提示由 errorHandler 统一处理
      // 此处只需刷新验证码
      if (initialState?.captchaEnabled) fetchCaptcha();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      {/* 左侧品牌区域 */}
      <div className={styles.leftSection}>
        <div className={styles.leftContent}>
          <div className={styles.brandLogo}>
            <span className={styles.logoText}>{PROJECT_TITLE}</span>
          </div>
          <h1 className={styles.slogan}>现代化后台管理系统</h1>
          <p className={styles.description}>
            {PROJECT_TITLE} 是一套基于 Umi Max
            的全栈解决方案，提供开箱即用的权限管理、CRUD 示例和认证体系。
          </p>
          <div className={styles.featureList}>
            <div className={styles.featureItem}>
              <span className={styles.featureDot} />
              基于 React 18 + Umi Max 4
            </div>
            <div className={styles.featureItem}>
              <span className={styles.featureDot} />
              内置权限管理与路由守卫
            </div>
            <div className={styles.featureItem}>
              <span className={styles.featureDot} />
              开箱即用的 CRUD 范式
            </div>
            <div className={styles.featureItem}>
              <span className={styles.featureDot} />
              前后端联调无缝对接
            </div>
          </div>
        </div>
      </div>

      {/* 右侧表单区域 */}
      <div className={styles.rightSection}>
        <div className={styles.formWrapper}>
          <LoginForm
            logo={false}
            title={PROJECT_TITLE}
            subTitle="欢迎回来，请登录您的账户"
            onFinish={handleSubmit}
            submitter={{
              searchConfig: { submitText: '登录' },
              submitButtonProps: {
                loading,
                size: 'large',
                block: true,
                className: styles.submitBtn,
              },
            }}
          >
            <Tabs
              activeKey={loginType}
              onChange={(key) => setLoginType(key)}
              centered
              items={[
                { key: 'account', label: '账号密码登录' },
                { key: 'mobile', label: '手机号登录' },
              ]}
            />
            {loginType === 'account' && (
              <>
                <ProFormText
                  name="username"
                  fieldProps={{
                    size: 'large',
                    prefix: <UserOutlined className={styles.inputIcon} />,
                  }}
                  placeholder="用户名: admin"
                  rules={[{ required: true, message: '请输入用户名' }]}
                />
                <ProFormText.Password
                  name="password"
                  fieldProps={{
                    size: 'large',
                    prefix: <LockOutlined className={styles.inputIcon} />,
                  }}
                  placeholder="密码: admin123"
                  rules={[{ required: true, message: '请输入密码' }]}
                />
              </>
            )}
            {loginType === 'mobile' && (
              <>
                <ProFormText
                  name="mobile"
                  fieldProps={{
                    size: 'large',
                    prefix: <MobileOutlined className={styles.inputIcon} />,
                    maxLength: 11,
                  }}
                  placeholder="手机号"
                  rules={[{ required: true, message: '请输入手机号' }]}
                />
                <ProFormText
                  name="code"
                  fieldProps={{
                    size: 'large',
                    prefix: <LockOutlined className={styles.inputIcon} />,
                  }}
                  placeholder="验证码"
                  rules={[{ required: true, message: '请输入验证码' }]}
                />
              </>
            )}
            {initialState?.captchaEnabled &&
              captchaImage &&
              loginType === 'account' && (
                <Space align="start" className={styles.captchaWrapper}>
                  <ProFormText
                    name="captcha"
                    fieldProps={{
                      size: 'large',
                      prefix: (
                        <SafetyCertificateOutlined
                          className={styles.inputIcon}
                        />
                      ),
                    }}
                    placeholder="验证码"
                    rules={[{ required: true, message: '请输入验证码' }]}
                  />
                  <Image
                    src={`data:image/png;base64,${captchaImage}`}
                    width={120}
                    height={40}
                    preview={false}
                    onClick={fetchCaptcha}
                    className={styles.captchaImage}
                  />
                </Space>
              )}
            <div className={styles.formActions}>
              <ProFormCheckbox name="remember">记住我</ProFormCheckbox>
              <a className={styles.forgotLink}>忘记密码？</a>
            </div>
          </LoginForm>
          <div className={styles.socialLogin}>
            <Divider>
              <span className={styles.socialDividerText}>其他登录方式</span>
            </Divider>
            <div className={styles.socialIcons}>
              <AlipayOutlined className={styles.socialIcon} />
              <TaobaoOutlined className={styles.socialIcon} />
              <WeiboOutlined className={styles.socialIcon} />
            </div>
          </div>
          <div className={styles.footer}>Copyright © 2024 {PROJECT_TITLE}</div>
        </div>
      </div>
    </div>
  );
}
