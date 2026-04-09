<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Ошибка входа'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-100">
    <div class="w-full max-w-sm">
      <div class="bg-white rounded-2xl shadow-lg p-8">
        <h1 class="text-xl font-bold text-blue-600 mb-1">Топмашина</h1>
        <p class="text-sm text-slate-400 mb-6">Вход в админ-панель</p>

        <form @submit.prevent="onSubmit" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1">Email</label>
            <input
              v-model="email"
              type="email"
              required
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              placeholder="admin@topmashina.ru"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1">Пароль</label>
            <input
              v-model="password"
              type="password"
              required
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {{ loading ? 'Вход...' : 'Войти' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
