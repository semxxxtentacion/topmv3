<script setup lang="ts">
import { reactive, computed } from 'vue'

const props = defineProps<{
  initialForm: {
    target_site: string
    keyword: string
    daily_visit_target: number | null
    total_visit_target: number | null
  }
  appId: number
}>()

const emit = defineEmits<{
  createTask: [appId: number, form: typeof form]
  cancel: []
}>()

const form = reactive({
  target_site: props.initialForm.target_site,
  keyword: props.initialForm.keyword,
  daily_visit_target: props.initialForm.daily_visit_target,
  total_visit_target: props.initialForm.total_visit_target,
})

const isValid = computed(() =>
  form.target_site && form.keyword && form.daily_visit_target && form.daily_visit_target > 0 && form.total_visit_target && form.total_visit_target > 0
)
</script>

<template>
  <div class="mt-3 bg-white rounded-lg border border-slate-200 p-4 space-y-3">
    <h5 class="text-xs font-bold text-slate-600">Новая задача</h5>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <label class="block text-xs text-slate-500 mb-1">Целевой сайт</label>
        <input
          v-model="form.target_site"
          placeholder="example.com"
          class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>
      <div>
        <label class="block text-xs text-slate-500 mb-1">Ключевая фраза</label>
        <input
          v-model="form.keyword"
          placeholder="купить квартиру москва"
          class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <label class="block text-xs text-slate-500 mb-1">Заходов в день</label>
        <input
          v-model.number="form.daily_visit_target"
          type="number"
          min="1"
          required
          placeholder="Введите кол-во"
          class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>
      <div>
        <label class="block text-xs text-slate-500 mb-1">Всего визитов (цель)</label>
        <input
          v-model.number="form.total_visit_target"
          type="number"
          min="1"
          required
          placeholder="Введите кол-во"
          class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>
    </div>

    <p class="text-xs text-slate-400">
      Прокси будет назначен автоматически из списка прокси проекта
    </p>

    <div class="flex gap-2">
      <button
        @click="emit('createTask', appId, form)"
        :disabled="!isValid"
        class="px-4 py-1.5 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 cursor-pointer"
      >
        Создать задачу
      </button>
      <button
        @click="$emit('cancel')"
        class="px-4 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-slate-100 cursor-pointer"
      >
        Отмена
      </button>
    </div>
  </div>
</template>
