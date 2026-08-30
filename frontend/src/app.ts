// 运行时配置
import { message } from 'antd';

function providerErrorMessage(errorCode: unknown): string | undefined {
  const normalizedCode = String(errorCode ?? '').toUpperCase();
  switch (normalizedCode) {
    case 'PROVIDER_UNAVAILABLE':
    case '502':
      return '上游服务繁忙，请稍后重试';
    case 'PROVIDER_UNHEALTHY':
    case '503':
      return '当前默认供应商暂不可用，请稍后重试';
    case 'PROVIDER_RATE_LIMITED':
    case '429':
      return '当前生成请求较多，请稍后重试';
    case 'PROVIDER_NOT_CONFIGURED':
    case 'PROVIDER_AUTH_FAILED':
    case 'PROVIDER_SUBMIT_FAILED':
    case 'PROVIDER_POLL_FAILED':
      return '请检查网络连接或服务端配置';
    default:
      return undefined;
  }
}

// 全局初始化数据配置，用于 Layout 用户信息和权限初始化
export async function getInitialState(): Promise<{
  currentUser?: API.UserInfo;
  captchaEnabled?: boolean;
  authEnabled?: boolean;
  ssoEnabled?: boolean;
}> {
  // 工作台无需登录；若由应用广场嵌入，认证头仍由请求拦截器透传。
  return {};
}

// request 全局错误处理
export const request = {
  requestInterceptors: [
    (config: any) => {
      const token = localStorage.getItem('token');
      config.headers = {
        ...config.headers,
        ...(token
          ? { Authorization: `Bearer ${token}` }
          : { 'X-Flowchart-User-Id': 'local-user' }),
      };
      return config;
    },
  ],
  errorConfig: {
    // 适配后端 Result 格式：HTTP 200 + body.code 判断成功/失败
    adaptor: (resData: any) => {
      return {
        success: resData.code === 200,
        errorMessage: resData.message || '请求失败',
        // 同时保留业务错误码与数值 code，页面可做稳定的用户提示，旧的全局处理仍可按 code 分支。
        code: resData.code,
        message: resData.message,
        errorCode: resData.errorCode || resData.code,
        data: resData.data,
      };
    },
    // 错误统一处理
    errorHandler: (error: any) => {
      const { response, data } = error;
      const errorCode = data?.errorCode || data?.code || response?.status;

      const friendlyProviderMessage = providerErrorMessage(errorCode);
      if (friendlyProviderMessage) {
        message.error(friendlyProviderMessage);
        throw error;
      }

      // 工作台不再跳转登录页；认证由宿主环境或后端本地模式决定。
      if (errorCode === 401) {
        message.error(data?.message || '当前请求未授权，请检查服务端认证配置');
        localStorage.removeItem('token');
        throw error;
      }

      // 403 无权限
      if (errorCode === 403) {
        message.error(data?.message || '当前用户没有权限执行此操作');
        throw error;
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
    // 工作台自带完整的三栏导航，隐藏后台模板的外层侧栏和折叠按钮。
    siderRender: false,
    menuRender: false,
    headerRender: false,
    collapsedButtonRender: false,
    contentStyle: { margin: 0, padding: 0 },
    menu: {
      locale: false,
    },
  };
};
