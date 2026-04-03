<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import api from '@/api/client'

const stats = ref<{ total: number; with_cookies: number; without_cookies: number } | null>(null)
const loading = ref(true)
let pollTimer: ReturnType<typeof setInterval> | null = null

async function loadStats() {
  try {
    const { data } = await api.get('/bot-profiles/stats')
    stats.value = data
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStats()
  pollTimer = setInterval(loadStats, 60000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <h2 class="text-xl font-bold text-slate-800 mb-6">Профили бота</h2>

    <div v-if="loading" class="text-sm text-slate-400">Загрузка...</div>

    <div v-else-if="stats" class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">Всего аккаунтов</div>
        <div class="text-2xl font-bold text-slate-800 mt-1">{{ stats.total }}</div>
      </div>

      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">С куками</div>
        <div class="text-2xl font-bold text-green-600 mt-1">{{ stats.with_cookies }}</div>
      </div>

      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">Без куков</div>
        <div class="text-2xl font-bold text-amber-500 mt-1">{{ stats.without_cookies }}</div>
      </div>
    </div>
  </div>
</template>
