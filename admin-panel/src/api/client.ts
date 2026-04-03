import axios from 'axios'
import router from '@/router'

const api = axios.create({
  baseURL: (import.meta.env.VITE_API_URL || 'https://топмашина.рф/api') + '/admin',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('admin_token')
      router.push('/login')
    }
    return Promise.reject(err)
  },
)

export default api
