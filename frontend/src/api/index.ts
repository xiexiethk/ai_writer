import axios from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'
import router from '@/router'

// 自动适配服务器地址，不再硬编码 IP
const baseURL = '/api'

const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    // 注入 JWT Token
    const token = localStorage.getItem('token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response
  },
  (error) => {
    // 401 自动跳转到登录页
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      router.push('/login')
    }
    
    // 统一错误处理
    const message = error.response?.data?.detail || error.response?.data?.message || error.message || '请求失败'
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)

export default apiClient

export * from './folder'
