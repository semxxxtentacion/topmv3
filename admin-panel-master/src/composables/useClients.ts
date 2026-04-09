import { ref, watch, onMounted } from 'vue'
import api from '@/api/client'
import type { Client } from '@/types'
import { usePagination } from './usePagination'

export function useClients() {
  const clients = ref<Client[]>([])
  const search = ref('')
  const loading = ref(true)
  const { page, total, limit, hasPages, hasPrev, hasNext, totalPages, offset, prev, next, reset } = usePagination()

  async function load() {
    loading.value = true
    try {
      const { data } = await api.get('/clients', {
        params: { limit, offset: offset.value, search: search.value || undefined },
      })
      clients.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  onMounted(load)

  let searchTimeout: ReturnType<typeof setTimeout>
  watch(search, () => {
    clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => {
      reset()
      load()
    }, 400)
  })

  function prevPage() {
    prev()
    load()
  }

  function nextPage() {
    next()
    load()
  }

  return { clients, search, loading, page, total, limit, hasPages, hasPrev, hasNext, totalPages, prevPage, nextPage, load }
}
