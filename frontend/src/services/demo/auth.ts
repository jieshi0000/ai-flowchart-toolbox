// 认证相关接口
import { request } from '@umijs/max';

// 类型定义
export namespace Auth {
  export interface LoginReq {
    username: string;
    password: string;
    captchaKey?: string;
    captchaCode?: string;
  }

  export interface LoginVO {
    userId: string;
    username: string;
    nickname: string;
    role: string;
    token: string;
  }

  export interface CaptchaVO {
    captchaKey: string;
    captchaImage: string;
  }

  export interface UserInfo {
    userId: string;
    username: string;
    nickname: string;
    phone?: string;
    role: string;
  }

  export interface PublicConfig {
    authEnabled: boolean;
    captchaEnabled: boolean;
    ssoEnabled: boolean;
  }
}

// API 响应格式（与后端 Result.java 对齐）
interface Result<T> {
  code: number;
  data: T;
  message?: string;
  timestamp?: number;
}

/** 获取公开配置（无需认证） */
export async function getPublicConfig() {
  return request<Result<Auth.PublicConfig>>('/api/public/config', {
    method: 'GET',
  });
}

/** 获取验证码 */
export async function getCaptcha() {
  return request<Result<Auth.CaptchaVO>>('/api/auth/captcha', {
    method: 'GET',
  });
}

/** 登录 */
export async function login(data: Auth.LoginReq) {
  return request<Result<Auth.LoginVO>>('/api/auth/login', {
    method: 'POST',
    data,
  });
}

/** 获取当前用户信息 */
export async function getMe() {
  return request<Result<Auth.UserInfo>>('/api/auth/me', {
    method: 'GET',
  });
}

/** 登出 */
export async function logout() {
  return request<Result<void>>('/api/auth/logout', {
    method: 'POST',
  });
}
