<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/api/client'
import type { DashboardStats } from '@/types'
import { formatMoney } from '@/utils/formatters'

const stats = ref<DashboardStats | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/stats/dashboard')
    stats.value = data
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h2 class="text-xl font-bold text-slate-800 mb-6">Дашборд</h2>

    <div v-if="loading" class="text-sm text-slate-400">Загрузка...</div>

    <div v-else-if="stats" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">Клиенты</div>
        <div class="text-2xl font-bold text-slate-800 mt-1">{{ stats.clients_count }}</div>
      </div>

      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">Ожидают рассмотрения</div>
        <div class="text-2xl font-bold text-amber-500 mt-1">{{ stats.pending_applications }}</div>
      </div>

      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">Всего заявок</div>
        <div class="text-2xl font-bold text-slate-800 mt-1">{{ stats.total_applications }}</div>
      </div>

      <div class="bg-white rounded-xl p-5 border border-slate-100 shadow-sm">
        <div class="text-sm text-slate-400">Выручка</div>
        <div class="text-2xl font-bold text-green-600 mt-1">{{ formatMoney(stats.total_revenue) }}</div>
        <div class="text-xs text-slate-400 mt-0.5">{{ stats.confirmed_payments }} платежей</div>
      </div>
    </div>
  </div>
</template>
