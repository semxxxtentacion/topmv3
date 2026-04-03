import { ref, onMounted } from 'vue'
import api from '@/api/client'
import type { Application } from '@/types'
import { usePagination } from './usePagination'

export function useApplications() {
  const apps = ref<Application[]>([])
  const filter = ref<string>('')
  const loading = ref(true)
  const { page, total, limit, hasPages, hasPrev, hasNext, totalPages, offset, prev, next, reset } = usePagination()

  async function load() {
    loading.value = true
    try {
      const params: Record<string, unknown> = { limit, offset: offset.value }
      if (filter.value) params.status = filter.value
      const { data } = await api.get('/applications', { params })
      apps.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  onMounted(load)

  async function setStatus(appId: number, status: string) {
    await api.patch(`/applications/${appId}/status`, { status })
    load()
  }

  function applyFilter(value: string) {
    filter.value = value
    reset()
    load()
  }

  function prevPage() {
    prev()
    load()
  }

  function nextPage() {
    next()
    load()
  }

  const filters = [
    { value: '', label: 'Все' },
    { value: 'pending', label: 'Ожидают' },
    { value: 'accepted', label: 'Принятые' },
    { value: 'rejected', label: 'Отклонённые' },
  ]

  return { apps, filter, loading, page, total, limit, hasPages, hasPrev, hasNext, totalPages, filters, load, setStatus, applyFilter, prevPage, nextPage }
}
