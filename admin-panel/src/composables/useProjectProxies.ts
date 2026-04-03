import { ref } from 'vue'
import api from '@/api/client'
import { useNotify } from '@/composables/useNotify'
import type { ProjectProxy } from '@/types'

export function useProjectProxies() {
  const { notify } = useNotify()
  const proxies = ref<Record<number, ProjectProxy[]>>({})
  const proxyFormVisible = ref<number | null>(null)
  const proxyFormUrl = ref('')
  const editingProxyId = ref<number | null>(null)
  const proxySaving = ref(false)
  const proxyCheckStatus = ref<Record<number, 'loading' | 'ok' | 'error'>>({})
  const proxyCheckIp = ref<Record<number, string>>({})
  const proxyCheckError = ref<Record<number, string>>({})

  async function loadProxies(appId: number) {
    try {
      const { data } = await api.get(`/projects/${appId}/proxies`)
      proxies.value[appId] = data.items
    } catch {
      proxies.value[appId] = []
    }
  }

  async function checkProxy(proxyId: number) {
    proxyCheckStatus.value[proxyId] = 'loading'
    try {
      const { data } = await api.post(`/project-proxies/${proxyId}/check`)
      if (data.status === 'ok') {
        proxyCheckStatus.value[proxyId] = 'ok'
        proxyCheckIp.value[proxyId] = data.ip
        delete proxyCheckError.value[proxyId]
      } else {
        proxyCheckStatus.value[proxyId] = 'error'
        proxyCheckError.value[proxyId] = data.error || 'Неизвестная ошибка'
      }
    } catch {
      proxyCheckStatus.value[proxyId] = 'error'
      proxyCheckError.value[proxyId] = 'Сервер недоступен'
    }
  }

  async function checkAllProxies(appIds: number[]) {
    const allProxies: ProjectProxy[] = []
    for (const appId of appIds) {
      const list = proxies.value[appId] || []
      allProxies.push(...list)
    }
    if (!allProxies.length) return
    await Promise.all(allProxies.map((p) => checkProxy(p.id)))
  }

  function openProxyForm(appId: number) {
    proxyFormVisible.value = appId
    proxyFormUrl.value = ''
    editingProxyId.value = null
  }

  function startEditProxy(proxy: ProjectProxy) {
    proxyFormVisible.value = proxy.application_id
    proxyFormUrl.value = proxy.proxy_url
    editingProxyId.value = proxy.id
  }

  function cancelProxyForm() {
    proxyFormVisible.value = null
    proxyFormUrl.value = ''
    editingProxyId.value = null
  }

  async function saveProxy(appId: number) {
    if (!proxyFormUrl.value.trim()) return
    proxySaving.value = true
    try {
      if (editingProxyId.value) {
        const { data } = await api.put(`/project-proxies/${editingProxyId.value}`, {
          proxy_url: proxyFormUrl.value.trim(),
        })
        const list = proxies.value[appId] || []
        const idx = list.findIndex((p) => p.id === editingProxyId.value)
        if (idx !== -1) list[idx] = data
        notify('Прокси обновлён', 'success')
      } else {
        const { data } = await api.post(`/projects/${appId}/proxies`, {
          proxy_url: proxyFormUrl.value.trim(),
        })
        if (!proxies.value[appId]) proxies.value[appId] = []
        proxies.value[appId].unshift(data)
        notify('Прокси добавлен', 'success')
        checkProxy(data.id)
      }
      cancelProxyForm()
    } finally {
      proxySaving.value = false
    }
  }

  async function deleteProxy(appId: number, proxyId: number) {
    if (!confirm('Удалить прокси?')) return
    await api.delete(`/project-proxies/${proxyId}`)
    proxies.value[appId] = (proxies.value[appId] || []).filter(
      (p) => p.id !== proxyId,
    )
    delete proxyCheckStatus.value[proxyId]
    delete proxyCheckIp.value[proxyId]
    notify('Прокси удалён', 'success')
  }

  return {
    proxies,
    proxyFormVisible,
    proxyFormUrl,
    editingProxyId,
    proxySaving,
    proxyCheckStatus,
    proxyCheckIp,
    proxyCheckError,
    loadProxies,
    openProxyForm,
    startEditProxy,
    cancelProxyForm,
    saveProxy,
    checkAllProxies,
    deleteProxy,
  }
}
