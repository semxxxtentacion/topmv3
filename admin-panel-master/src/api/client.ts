import axios from 'axios'
import router from '@/router'
import type { Partner, PartnerPayload } from '@/types'

export const API_ORIGIN = import.meta.env.VITE_API_URL || 'https://topmashina.ru/api'

export function resolveApiAsset(url: string | null | undefined): string {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/')) return `${API_ORIGIN}${url}`
  return url
}

const api = axios.create({
  baseURL: API_ORIGIN + '/admin',
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

// Partners API
export async function getPartners(): Promise<Partner[]> {
  const { data } = await api.get<Partner[]>('/partners')
  return data
}

export async function createPartner(payload: Partial<PartnerPayload>): Promise<Partner> {
  const { data } = await api.post<Partner>('/partners', payload)
  return data
}

export async function updatePartner(id: number, payload: Partial<PartnerPayload>): Promise<Partner> {
  const { data } = await api.patch<Partner>(`/partners/${id}`, payload)
  return data
}

export async function deletePartner(id: number): Promise<void> {
  await api.delete(`/partners/${id}`)
}

export async function uploadPartnerLogo(file: File): Promise<{ url: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post<{ url: string }>('/partners/upload-logo', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export default api
