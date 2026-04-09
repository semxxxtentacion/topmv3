<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api/client'

const route = useRoute()
const router = useRouter()

const token = route.query.token as string
const name = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await api.post('/auth/register', {
      token,
      name: name.value,
      password: password.value,
    })
    done.value = true
    setTimeout(() => router.push('/login'), 2000)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Ошибка регистрации'
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
        <p class="text-sm text-slate-400 mb-6">Создание аккаунта по приглашению</p>

        <div v-if="!token" class="text-sm text-red-500">
          Невалидная ссылка приглашения
        </div>

        <div v-else-if="done" class="text-sm text-green-600">
          Аккаунт создан! Перенаправляем на страницу входа...
        </div>

        <form v-else @submit.prevent="onSubmit" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1">Имя</label>
            <input
              v-model="name"
              type="text"
              required
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-600 mb-1">Пароль</label>
            <input
              v-model="password"
              type="password"
              required
              minlength="6"
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {{ loading ? 'Создание...' : 'Создать аккаунт' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
