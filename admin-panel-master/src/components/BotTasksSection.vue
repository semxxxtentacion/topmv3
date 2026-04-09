<script setup lang="ts">
import type { BotTask } from '@/types'
import { taskStatusLabel, taskStatusClass } from '@/utils/formatters'

defineProps<{
  tasks: BotTask[]
  loading: boolean
}>()

defineEmits<{
  addTask: []
  autoGenerate: []
  togglePause: [task: BotTask]
  deleteTask: [taskId: number]
}>()
</script>

<template>
  <div class="mt-4 bg-blue-50/50 rounded-xl border border-blue-100 p-4">
    <div class="flex items-center justify-between mb-3">
      <h4 class="text-sm font-bold text-slate-700">
        Задачи бота
        <span class="text-slate-400 font-normal">({{ tasks.length }})</span>
      </h4>
      <div class="flex gap-2">
        <button
          @click="$emit('autoGenerate')"
          class="px-3 py-1 text-xs bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 cursor-pointer"
        >
          Авто-генерация
        </button>
        <button
          @click="$emit('addTask')"
          class="px-3 py-1 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600 cursor-pointer"
        >
          Добавить задачу
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-xs text-slate-400">
      Загрузка задач...
    </div>

    <table v-else-if="tasks.length" class="w-full text-xs">
      <thead class="text-slate-500">
        <tr>
          <th class="text-left py-1.5 px-2">Фраза</th>
          <th class="text-left py-1.5 px-2">Сайт</th>
          <th class="text-left py-1.5 px-2">Сегодня</th>
          <th class="text-left py-1.5 px-2">Цель визитов</th>
          <th class="text-left py-1.5 px-2">Всего</th>
          <th class="text-left py-1.5 px-2">Статус</th>
          <th class="text-right py-1.5 px-2">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="task in tasks"
          :key="task.id"
          class="border-t border-blue-100/50"
        >
          <td class="py-1.5 px-2 font-medium max-w-40 truncate">
            {{ task.keyword }}
          </td>
          <td class="py-1.5 px-2 text-slate-500 max-w-32 truncate">
            {{ task.target_site }}
          </td>
          <td class="py-1.5 px-2">
            <span class="text-slate-600">{{ task.daily_visit_count }}</span>
            <span class="text-slate-400">/{{ task.daily_visit_target }}</span>
          </td>
          <td class="py-1.5 px-2">
            <span class="text-slate-600">{{ task.total_visit_target }}</span>
          </td>
          <td class="py-1.5 px-2">
            <span class="text-green-600">{{ task.successful_visits ?? '—' }}</span>
            <span v-if="task.failed_visits" class="text-red-500 ml-1">/{{ task.failed_visits }} err</span>
          </td>
          <td class="py-1.5 px-2">
            <span
              class="px-2 py-0.5 rounded-full text-xs font-medium"
              :class="taskStatusClass(task)"
            >
              {{ taskStatusLabel(task) }}
            </span>
          </td>
          <td class="py-1.5 px-2 text-right">
            <div class="flex gap-1 justify-end">
              <button
                @click="$emit('togglePause', task)"
                class="px-2 py-0.5 text-xs border border-slate-200 rounded hover:bg-blue-50 cursor-pointer"
              >
                {{ task.is_paused ? 'Запустить' : 'Пауза' }}
              </button>
              <button
                @click="$emit('deleteTask', task.id)"
                class="px-2 py-0.5 text-xs border border-red-200 text-red-500 rounded hover:bg-red-50 cursor-pointer"
              >
                Удалить
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else-if="!loading" class="text-xs text-slate-400">
      Нет задач
    </div>

    <slot />
  </div>
</template>