import { ref, onMounted } from 'vue'
import {
  getPartners,
  createPartner,
  updatePartner,
  deletePartner,
  uploadPartnerLogo,
} from '@/api/client'
import { useNotify } from '@/composables/useNotify'
import type { Partner, PartnerPayload } from '@/types'

function emptyForm(): PartnerPayload {
  return {
    slug: '',
    name: '',
    logo_url: '',
    short_description: '',
    full_description: '',
    website_url: null,
    sort_order: 0,
    is_active: true,
  }
}

export function usePartners() {
  const { notify } = useNotify()

  const partners = ref<Partner[]>([])
  const loading = ref(true)
  const saving = ref(false)
  const uploading = ref(false)

  const showForm = ref(false)
  const editingId = ref<number | null>(null)
  const form = ref<PartnerPayload>(emptyForm())

  async function load() {
    loading.value = true
    try {
      partners.value = await getPartners()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      notify(err.response?.data?.detail || 'Не удалось загрузить партнёров', 'error')
    } finally {
      loading.value = false
    }
  }

  onMounted(load)

  function openCreate() {
    editingId.value = null
    form.value = emptyForm()
    showForm.value = true
  }

  function openEdit(p: Partner) {
    editingId.value = p.id
    form.value = {
      slug: p.slug,
      name: p.name,
      logo_url: p.logo_url,
      short_description: p.short_description,
      full_description: p.full_description,
      website_url: p.website_url,
      sort_order: p.sort_order,
      is_active: p.is_active,
    }
    showForm.value = true
  }

  function closeForm() {
    showForm.value = false
    editingId.value = null
    form.value = emptyForm()
  }

  async function uploadLogo(file: File) {
    uploading.value = true
    try {
      const { url } = await uploadPartnerLogo(file)
      form.value.logo_url = url
      notify('Логотип загружен', 'success', 1500)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      notify(err.response?.data?.detail || 'Ошибка загрузки логотипа', 'error')
    } finally {
      uploading.value = false
    }
  }

  async function save() {
    if (!form.value.name.trim()) {
      notify('Введите название партнёра', 'error')
      return
    }
    if (!form.value.logo_url) {
      notify('Загрузите логотип', 'error')
      return
    }

    saving.value = true
    try {
      // Не отправляем пустой slug — пусть бэк сгенерирует
      const payload: Partial<PartnerPayload> = { ...form.value }
      if (!payload.slug) delete payload.slug
      if (!payload.website_url) payload.website_url = null

      if (editingId.value != null) {
        const updated = await updatePartner(editingId.value, payload)
        const idx = partners.value.findIndex((p) => p.id === updated.id)
        if (idx !== -1) partners.value[idx] = updated
        notify('Партнёр обновлён', 'success')
      } else {
        const created = await createPartner(payload)
        partners.value.push(created)
        notify('Партнёр создан', 'success')
      }
      closeForm()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      notify(err.response?.data?.detail || 'Ошибка сохранения', 'error')
    } finally {
      saving.value = false
    }
  }

  async function toggleActive(p: Partner) {
    const next = !p.is_active
    try {
      const updated = await updatePartner(p.id, { is_active: next })
      const idx = partners.value.findIndex((x) => x.id === p.id)
      if (idx !== -1) partners.value[idx] = updated
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      notify(err.response?.data?.detail || 'Ошибка обновления', 'error')
    }
  }

  async function remove(p: Partner) {
    if (!confirm(`Удалить партнёра «${p.name}»?`)) return
    try {
      await deletePartner(p.id)
      partners.value = partners.value.filter((x) => x.id !== p.id)
      notify('Партнёр удалён', 'success')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      notify(err.response?.data?.detail || 'Ошибка удаления', 'error')
    }
  }

  return {
    partners,
    loading,
    saving,
    uploading,
    showForm,
    editingId,
    form,
    load,
    openCreate,
    openEdit,
    closeForm,
    uploadLogo,
    save,
    toggleActive,
    remove,
  }
}
