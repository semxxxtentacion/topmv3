<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useApplications } from '@/composables/useApplications'
import { statusLabel, statusClass } from '@/utils/formatters'

const router = useRouter()
const { apps, filter, loading, page, total, limit, hasPages, hasPrev, hasNext, totalPages, filters, setStatus, applyFilter, prevPage, nextPage } = useApplications()

function goToClient(userId: number) {
  router.push(`/clients/${userId}`)
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-slate-800">Заявки</h2>
      <span class="text-sm text-slate-400">Всего: {{ total }}</span>
    </div>

    <!-- Filters -->
    <div class="flex gap-2 mb-4">
      <button
        v-for="f in filters"
        :key="f.value"
        @click="applyFilter(f.value)"
        class="px-3 py-1.5 text-sm rounded-lg border transition-colors cursor-pointer"
        :class="filter === f.value
          ? 'bg-blue-500 text-white border-blue-500'
          : 'border-slate-200 text-slate-600 hover:bg-blue-50'"
      >
        {{ f.label }}
      </button>
    </div>

    <div class="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500">
          <tr>
            <th class="text-left px-4 py-3 font-medium">ID</th>
            <th class="text-left px-4 py-3 font-medium">Клиент</th>
            <th class="text-left px-4 py-3 font-medium">Сайт</th>
            <th class="text-left px-4 py-3 font-medium">Регион</th>
            <th class="text-left px-4 py-3 font-medium">Статус</th>
            <th class="text-left px-4 py-3 font-medium">Менеджер</th>
            <th class="text-left px-4 py-3 font-medium">Дата</th>
            <th class="text-left px-4 py-3 font-medium">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="a in apps"
            :key="a.id"
            class="border-t border-slate-50 hover:bg-blue-50 cursor-pointer transition-colors"
            @click="goToClient(a.user_id)"
          >
            <td class="px-4 py-3 text-slate-400">#{{ a.id }}</td>
            <td class="px-4 py-3 text-blue-500">
              {{ a.client_email || '—' }}
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <span>{{ a.site }}</span>
                <span
                  v-if="a.is_duplicate"
                  class="px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/20 text-red-500"
                  title="Этот сайт зарегистрирован у нескольких пользователей"
                >
                  Дубль
                </span>
              </div>
            </td>
            <td class="px-4 py-3">{{ a.region || '—' }}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="statusClass(a.status)">
                {{ statusLabel(a.status) }}
              </span>
            </td>
            <td class="px-4 py-3">{{ a.manager_name || '—' }}</td>
            <td class="px-4 py-3 text-slate-400">{{ new Date(a.created_at).toLocaleDateString('ru') }}</td>
            <td class="px-4 py-3">
              <div v-if="!a.status" class="flex gap-1">
                <button
                  @click.stop="setStatus(a.id, 'accepted')"
                  class="px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600 cursor-pointer"
                >
                  Принять
                </button>
                <button
                  @click.stop="setStatus(a.id, 'rejected')"
                  class="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 cursor-pointer"
                >
                  Отклонить
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!apps.length && !loading">
            <td colspan="8" class="px-4 py-8 text-center text-slate-400">Нет заявок</td>
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
