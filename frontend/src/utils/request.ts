import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

/**
 * Axios 请求封装
 *
 * 类比：Spring RestTemplate + Interceptor
 * - 请求拦截器 ≈ ClientHttpRequestInterceptor（自动注入 Token）
 * - 响应拦截器 ≈ ResponseErrorHandler（统一错误处理）
 * - 401 处理 ≈ Spring Security 的 AuthenticationEntryPoint
 */

/** 统一响应格式 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 创建 Axios 实例 */
const instance: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ========== 请求拦截器 ==========
instance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 从 Pinia Store 获取 token（而非直接读 localStorage）
    // Pinia 在 setup 外使用需要特别注意：必须在 app.use(pinia) 之后调用
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  },
)

// ========== 响应拦截器 ==========
instance.interceptors.response.use(
  (response) => {
    // 后端统一返回 { code, message, data }
    const res = response.data as ApiResponse

    // 业务状态码非 200 视为异常
    if (res.code !== undefined && res.code !== 200) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }

    return response
  },
  (error: AxiosError) => {
    const { response } = error

    if (response) {
      const { status } = response

      switch (status) {
        case 401: {
          // Token 过期或无效 → 清除登录态 → 跳转登录页
          const authStore = useAuthStore()
          authStore.logout()
          ElMessage.error('登录已过期，请重新登录')
          // 使用 window.location 避免循环依赖 router
          window.location.hash = '#/login'
          break
        }
        case 403:
          ElMessage.error('没有操作权限')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 500:
          ElMessage.error('服务器内部错误')
          break
        default:
          ElMessage.error(`请求失败 (${status})`)
      }
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请稍后重试')
    } else {
      ElMessage.error('网络异常，请检查网络连接')
    }

    return Promise.reject(error)
  },
)

export default instance