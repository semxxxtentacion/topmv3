<script setup lang="ts">
defineProps<{
  editForm: {
    site: string
    region: string
    keywords: string
    audit: boolean
    google: boolean
    yandex: boolean
    keywords_selection: boolean
    total_visits?: number | null
  }
  editSaving: boolean
  citySearch: string
  sortedCities: [string, string][]
  cities: Record<string, string>
}>()

defineEmits<{
  save: []
  cancel: []
  selectCity: [name: string, id: string]
  'update:citySearch': [value: string]
}>()
</script>

<template>
  <div class="mt-4 bg-slate-50 rounded-xl p-5 space-y-4">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div>
        <label class="block text-xs text-slate-500 mb-1">Сайт</label>
        <input
          v-model="editForm.site"
          class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>
      <div class="relative">
        <label class="block text-xs text-slate-500 mb-1">Регион</label>
        <input
          :value="citySearch"
          @input="$emit('update:citySearch', ($event.target as HTMLInputElement).value)"
          :placeholder="editForm.region || 'Поиск города...'"
          class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          @focus="$emit('update:citySearch', '')"
        />
        <div
          v-if="editForm.region && !citySearch"
          class="text-xs text-slate-400 mt-1"
        >
          Выбран: {{ editForm.region }} ({{
            cities[editForm.region] || '—'
          }})
        </div>
        <div
          v-if="citySearch"
          class="absolute z-10 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-auto"
        >
          <button
            v-for="[name, id] in sortedCities.slice(0, 50)"
            :key="id"
            @click="$emit('selectCity', name, id)"
            class="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer"
          >
            {{ name }} <span class="text-slate-400">({{ id }})</span>
          </button>
          <div
            v-if="!sortedCities.length"
            class="px-3 py-2 text-sm text-slate-400"
          >
            Ничего не найдено
          </div>
        </div>
      </div>
      <div>
        <label class="block text-xs text-slate-500 mb-1">Переходов всего (на проект)</label>
        <input
          v-model.number="editForm.total_visits"
          type="number"
          placeholder="Например: 1000"
          class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>
    </div>

    <div>
      <label class="block text-xs text-slate-500 mb-1">Ключевые слова</label>
      <textarea
        v-model="editForm.keywords"
        rows="6"
        class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 font-mono"
      ></textarea>
    </div>

    <div class="flex flex-wrap gap-4">
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" v-model="editForm.google" class="accent-blue-500" />
        Google
      </label>
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" v-model="editForm.yandex" class="accent-blue-500" />
        Yandex
      </label>
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" v-model="editForm.audit" class="accent-blue-500" />
        Аудит
      </label>
      <label class="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" v-model="editForm.keywords_selection" class="accent-blue-500" />
        Подбор слов
      </label>
    </div>

    <div class="flex gap-2">
      <button
        @click="$emit('save')"
        :disabled="editSaving"
        class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 cursor-pointer"
      >
        {{ editSaving ? 'Сохранение...' : 'Сохранить' }}
      </button>
      <button
        @click="$emit('cancel')"
        class="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-100 cursor-pointer"
      >
        Отмена
      </button>
    </div>
  </div>
</template>