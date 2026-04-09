import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('admin_token') || '')
  const name = ref('')
  const role = ref('')

  const isAuth = computed(() => !!token.value)

  async function login(email: string, password: string) {
    const { data } = await api.post('/auth/login', { email, password })
    token.value = data.access_token
    name.value = data.name
    role.value = data.role
    localStorage.setItem('admin_token', data.access_token)
  }

  async function fetchMe() {
    try {
      const { data } = await api.get('/auth/me')
      name.value = data.name
      role.value = data.role
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    name.value = ''
    role.value = ''
    localStorage.removeItem('admin_token')
    router.push('/login')
  }

  return { token, name, role, isAuth, login, fetchMe, logout }
})
