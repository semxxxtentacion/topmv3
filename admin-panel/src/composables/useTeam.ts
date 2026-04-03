import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/client'
import type { TeamMember } from '@/types'

export function useTeam() {
  const auth = useAuthStore()
  const team = ref<TeamMember[]>([])
  const loading = ref(true)

  // Invite state
  const showInvite = ref(false)
  const inviteEmail = ref('')
  const inviteRole = ref('manager')
  const inviteLoading = ref(false)
  const inviteMsg = ref('')
  const inviteErr = ref('')

  const canInvite = ['admin', 'superadmin'].includes(auth.role)

  async function load() {
    loading.value = true
    try {
      const { data } = await api.get('/team')
      team.value = data.items
    } finally {
      loading.value = false
    }
  }

  onMounted(load)

  async function sendInvite() {
    inviteErr.value = ''
    inviteMsg.value = ''
    inviteLoading.value = true
    try {
      const { data } = await api.post('/auth/invite', {
        email: inviteEmail.value,
        role: inviteRole.value,
      })
      inviteMsg.value = data.message
      inviteEmail.value = ''
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      inviteErr.value = err.response?.data?.detail || 'Ошибка'
    } finally {
      inviteLoading.value = false
    }
  }

  async function deactivate(id: number) {
    if (!confirm('Деактивировать пользователя?')) return
    await api.delete(`/team/${id}`)
    load()
  }

  return {
    auth, team, loading,
    showInvite, inviteEmail, inviteRole, inviteLoading, inviteMsg, inviteErr,
    canInvite,
    load, sendInvite, deactivate,
  }
}
