import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/client'
import { getCities } from '@/utils/cities'
import { useNotify } from '@/composables/useNotify'
import type { Client, Application, Payment } from '@/types'

interface EditForm {
  site: string
  region: string
  keywords: string
  audit: boolean
  google: boolean
  yandex: boolean
  keywords_selection: boolean
  _region_id?: number
}

export function useClientDetail(clientId: number) {
  const router = useRouter()
  const { notify } = useNotify()

  const client = ref<Client | null>(null)
  const applications = ref<Application[]>([])
  const payments = ref<Payment[]>([])
  const loading = ref(true)

  // Cities
  const cities = getCities() as Record<string, string>
  const citySearch = ref('')
  const sortedCities = computed(() => {
    const entries = Object.entries(cities).sort((a, b) =>
      a[0].localeCompare(b[0], 'ru'),
    )
    if (!citySearch.value) return entries
    const q = citySearch.value.toLowerCase()
    return entries.filter(([name]) => name.toLowerCase().includes(q))
  })

  // Editing state
  const editingId = ref<number | null>(null)
  const editForm = ref<EditForm>({} as EditForm)
  const editSaving = ref(false)

  async function loadClient() {
    loading.value = true
    try {
      const { data } = await api.get(`/clients/${clientId}`)
      client.value = data.client
      applications.value = data.applications
      payments.value = data.payments
      return data.applications as Application[]
    } finally {
      loading.value = false
    }
  }

  async function deleteClient() {
    if (
      !confirm(
        `Удалить клиента ${client.value!.email}? Все его проекты и платежи будут удалены.`,
      )
    )
      return
    await api.delete(`/clients/${clientId}`)
    router.push('/clients')
  }

  async function sendReset() {
    const { data } = await api.post(`/clients/${clientId}/reset-password`)
    notify(data.message, 'success')
  }

  async function deleteApplication(appId: number) {
    if (!confirm('Удалить проект? Все задачи бота будут удалены.')) return
    await api.delete(`/applications/${appId}`)
    applications.value = applications.value.filter((a) => a.id !== appId)
    notify('Проект удалён', 'success')
  }

  function startEdit(app: Application) {
    if (editingId.value === app.id) {
      editingId.value = null
      return
    }
    editingId.value = app.id
    citySearch.value = ''
    editForm.value = {
      site: app.site || '',
      region: app.region || '',
      keywords: app.keywords || '',
      audit: app.audit ?? false,
      google: app.google ?? false,
      yandex: app.yandex ?? false,
      keywords_selection: app.keywords_selection ?? false,
    }
  }

  function selectCity(name: string, id: string) {
    editForm.value.region = name
    editForm.value._region_id = Number(id)
    citySearch.value = ''
  }

  async function saveEdit(appId: number) {
    editSaving.value = true
    try {
      const regionId =
        editForm.value._region_id ??
        (cities[editForm.value.region]
          ? Number(cities[editForm.value.region])
          : undefined)
      const payload: Record<string, unknown> = {
        site: editForm.value.site,
        region: editForm.value.region,
        keywords: editForm.value.keywords,
        audit: editForm.value.audit,
        google: editForm.value.google,
        yandex: editForm.value.yandex,
        keywords_selection: editForm.value.keywords_selection,
      }
      if (regionId) payload.region_id = regionId

      await api.patch(`/projects/${appId}`, payload)

      const idx = applications.value.findIndex((a) => a.id === appId)
      if (idx !== -1 && applications.value[idx]) {
        Object.assign(applications.value[idx], payload)
      }
      editingId.value = null
      notify('Проект обновлён', 'success')
    } finally {
      editSaving.value = false
    }
  }

  return {
    client, applications, payments, loading,
    cities, citySearch, sortedCities,
    editingId, editForm, editSaving,
    loadClient, deleteClient, deleteApplication, sendReset, startEdit, selectCity, saveEdit,
  }
}
