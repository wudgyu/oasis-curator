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
    // 从 localStorage 读取 token（避免与 Pinia 循环依赖）
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

/** 从 FastAPI 错误响应中提取可读的错误信息 */
function extractErrorMessage(error: AxiosError): string | null {
  const data = error.response?.data as { detail?: unknown } | undefined
  if (!data || data.detail === undefined) return null

  const detail = data.detail
  if (typeof detail === 'string') {
    return detail
  }

  // 422 校验错误：detail 是数组 [{ loc, msg }]
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: string[]; msg?: string }
    const field = first.loc?.[first.loc.length - 1] ?? ''
    const msg = first.msg ?? '参数校验失败'
    return field ? `${field}: ${msg}` : msg
  }

  return null
}

instance.interceptors.response.use(
  (response) => {
    return response
  },
  (error: AxiosError) => {
    const { response } = error

    if (response) {
      const { status } = response
      // 登录接口自身返回 401 = 密码错误，不走全局"登录过期"逻辑
      const isLoginRequest = error.config?.url?.includes('/auth/login')

      switch (status) {
        case 401: {
          if (!isLoginRequest) {
            // Token 过期或无效 → 清除登录态 → 跳转登录页
            const authStore = useAuthStore()
            authStore.clearAuthState()
            ElMessage.error('登录已过期，请重新登录')
            // 使用 window.location 避免循环依赖 router
            window.location.hash = '#/login'
          } else {
            ElMessage.error(extractErrorMessage(error) ?? '用户名或密码错误')
          }
          break
        }
        case 403:
          ElMessage.error(extractErrorMessage(error) ?? '没有操作权限')
          break
        case 404:
          ElMessage.error(extractErrorMessage(error) ?? '请求的资源不存在')
          break
        case 409:
          ElMessage.error(extractErrorMessage(error) ?? '数据冲突')
          break
        case 422:
          ElMessage.error(extractErrorMessage(error) ?? '参数校验失败')
          break
        case 500:
          ElMessage.error('服务器内部错误')
          break
        default:
          ElMessage.error(extractErrorMessage(error) ?? `请求失败 (${status})`)
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