<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useClients } from '@/composables/useClients'

const router = useRouter()
const { clients, search, loading, page, total, limit, hasPages, hasPrev, hasNext, totalPages, prevPage, nextPage } = useClients()

function goTo(id: number) {
  router.push(`/clients/${id}`)
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-slate-800">Клиенты</h2>
      <span class="text-sm text-slate-400">Всего: {{ total }}</span>
    </div>

    <input
      v-model="search"
      type="text"
      placeholder="Поиск по email, имени, телефону..."
      class="w-full max-w-md px-3 py-2 border border-slate-200 rounded-lg text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-300"
    />

    <div class="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500">
          <tr>
            <th class="text-left px-4 py-3 font-medium">ID</th>
            <th class="text-left px-4 py-3 font-medium">Email</th>
            <th class="text-left px-4 py-3 font-medium">Имя</th>
            <th class="text-left px-4 py-3 font-medium">Телефон</th>
            <th class="text-left px-4 py-3 font-medium">Баланс</th>
            <th class="text-left px-4 py-3 font-medium">Дата</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in clients"
            :key="c.id"
            @click="goTo(c.id)"
            class="border-t border-slate-50 hover:bg-blue-50 cursor-pointer transition-colors"
          >
            <td class="px-4 py-3 text-slate-400">#{{ c.id }}</td>
            <td class="px-4 py-3">{{ c.email }}</td>
            <td class="px-4 py-3">{{ c.name || '—' }}</td>
            <td class="px-4 py-3">{{ c.phone || '—' }}</td>
            <td class="px-4 py-3">{{ c.applications_balance }}</td>
            <td class="px-4 py-3 text-slate-400">{{ new Date(c.created_at).toLocaleDateString('ru') }}</td>
          </tr>
          <tr v-if="!clients.length && !loading">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">Нет клиентов</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="hasPages" class="flex gap-2 mt-4 justify-center">
      <button
        :disabled="!hasPrev"
        @click="prevPage()"
        class="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-30 hover:bg-blue-50 cursor-pointer"
      >
        Назад
      </button>
      <span class="px-3 py-1.5 text-sm text-slate-400">
        {{ page + 1 }} / {{ totalPages }}
      </span>
      <button
        :disabled="!hasNext"
        @click="nextPage()"
        class="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-30 hover:bg-blue-50 cursor-pointer"
      >
        Вперёд
      </button>
    </div>
  </div>
</template>
