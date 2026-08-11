// 运行时配置
import { getMe, getPublicConfig } from '@/services/demo/auth';
import { history } from '@umijs/max';
import { message } from 'antd';

// 全局初始化数据配置，用于 Layout 用户信息和权限初始化
export async function getInitialState(): Promise<{
  currentUser?: API.UserInfo;
  captchaEnabled?: boolean;
  authEnabled?: boolean;
  ssoEnabled?: boolean;
}> {
  const { pathname } = history.location;

  // 登录页：获取公开配置（验证码开关等），不获取用户信息
  if (pathname === '/login') {
    try {
      const cfg = await getPublicConfig();
      if (cfg.code === 200) {
        return {
          captchaEnabled: cfg.data.captchaEnabled,
          authEnabled: cfg.data.authEnabled,
          ssoEnabled: cfg.data.ssoEnabled,
        };
      }
    } catch {
      // 公开配置获取失败，使用默认值
    }
    return {};
  }

  // 非登录页：获取用户信息
  try {
    const res = await getMe();
    if (res.code === 200) {
      return {
        currentUser: res.data,
      };
    }
    // code=401 说明未登录或 token 过期
    localStorage.removeItem('token');
    history.push('/login');
    return {};
  } catch {
    // 网络错误等，清除 token 跳登录页
    localStorage.removeItem('token');
    history.push('/login');
    return {};
  }
}

// request 全局错误处理
export const request = {
  requestInterceptors: [
    (config: any) => {
      const token = localStorage.getItem('token');
      if (token) {
        config.headers = {
          ...config.headers,
          Authorization: `Bearer ${token}`,
        };
      }
      return config;
    },
  ],
  errorConfig: {
    // 适配后端 Result 格式：HTTP 200 + body.code 判断成功/失败
    adaptor: (resData: any) => {
      return {
        success: resData.code === 200,
        errorMessage: resData.message || '请求失败',
        errorCode: resData.code,
        data: resData.data,
      };
    },
    // 错误统一处理
    errorHandler: (error: any) => {
      const { response, data } = error;
      const errorCode = data?.code || response?.status;

      // 401 未认证：后端返回 HTTP 200 + body.code=401
      if (errorCode === 401) {
        message.error('登录已过期，请重新登录');
        localStorage.removeItem('token');
        if (history.location.pathname !== '/login') {
          history.push('/login');
        }
        return;
      }

      // 403 无权限
      if (errorCode === 403) {
        history.push('/401');
        return;
      }

      // 500 服务器错误
      if (errorCode === 500) {
        message.error(data?.message || '服务器异常，请稍后重试');
        return;
      }

      // 其他业务错误（10001 验证码错误、10003 账号密码错误等）
      if (data?.message) {
        message.error(data.message);
      } else {
        message.error('请求失败，请稍后重试');
      }
      throw error;
    },
  },
};

export const layout = () => {
  return {
    logo: 'https://img.alicdn.com/tfs/TB1YHEpwUT1gK0jSZFhXXaAtVXa-28-27.svg',
    menu: {
      locale: false,
    },
  };
};
