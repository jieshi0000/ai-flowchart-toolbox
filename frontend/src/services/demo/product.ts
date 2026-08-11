// Demo 商品 CRUD 接口（对接后端 DemoController）
import { request } from '@umijs/max';

// 类型定义
export namespace DemoProduct {
  export interface VO {
    id: string;
    name: string;
    description?: string;
    price: number;
    stock: number;
    viewCount: number;
    isActive: boolean;
    status: string;
    publishDate?: string;
    categoryId?: string;
    tags?: string[];
    ratings?: number[];
    attributes?: Record<string, any>;
    createdAt: string;
    updatedAt: string;
  }

  export interface CreateReq {
    name: string;
    description?: string;
    price: number;
    stock: number;
    isActive: boolean;
    publishDate?: string;
    categoryId?: string;
    tags?: string[];
    ratings?: number[];
    attributes?: Record<string, any>;
  }

  export interface UpdateReq extends CreateReq {
    id: string;
    status?: string;
  }

  export interface PageReq {
    pageNum: number;
    pageSize: number;
    name?: string;
    status?: string;
    minPrice?: number;
    maxPrice?: number;
  }

  export interface PageResult {
    pageNum: number;
    pageSize: number;
    pages: number;
    total: number;
    records: VO[];
  }
}

// API 响应格式
interface Result<T> {
  code: number;
  data: T;
  message?: string;
}

/** 创建商品 */
export async function createProduct(data: DemoProduct.CreateReq) {
  return request<Result<string>>('/api/demo/create', {
    method: 'POST',
    data,
  });
}

/** 查询商品详情 */
export async function getProduct(id: string) {
  return request<Result<DemoProduct.VO>>('/api/demo/get', {
    method: 'GET',
    params: { id },
  });
}

/** 更新商品 */
export async function updateProduct(data: DemoProduct.UpdateReq) {
  return request<Result<void>>('/api/demo/update', {
    method: 'POST',
    data,
  });
}

/** 删除商品 */
export async function deleteProduct(id: string) {
  return request<Result<void>>('/api/demo/delete', {
    method: 'POST',
    params: { id },
  });
}

/** 分页查询 */
export async function pageProduct(params: DemoProduct.PageReq) {
  return request<Result<DemoProduct.PageResult>>('/api/demo/page', {
    method: 'GET',
    params,
  });
}

/** 列表查询 */
export async function listProduct(params?: {
  status?: string;
  categoryId?: string;
}) {
  return request<Result<DemoProduct.VO[]>>('/api/demo/list', {
    method: 'GET',
    params,
  });
}
