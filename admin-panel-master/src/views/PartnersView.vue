<script setup lang="ts">
import { ref } from 'vue'
import { usePartners } from '@/composables/usePartners'
import { resolveApiAsset } from '@/api/client'

const {
  partners,
  loading,
  saving,
  uploading,
  showForm,
  editingId,
  form,
  openCreate,
  openEdit,
  closeForm,
  uploadLogo,
  save,
  toggleActive,
  remove,
} = usePartners()

const fileInput = ref<HTMLInputElement | null>(null)

function onPickFile() {
  fileInput.value?.click()
}

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    uploadLogo(file)
  }
  // Сброс, чтобы можно было выбрать тот же файл повторно
  target.value = ''
}

function onBackdrop(e: MouseEvent) {
  if (e.target === e.currentTarget) closeForm()
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-slate-800">Партнёры</h2>
      <button
        @click="openCreate"
        class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 cursor-pointer"
      >
        Добавить партнёра
      </button>
    </div>

    <div v-if="loading" class="text-sm text-slate-400">Загрузка...</div>

    <div
      v-else
      class="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden"
    >
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500">
          <tr>
            <th class="text-left px-4 py-3 font-medium">Логотип</th>
            <th class="text-left px-4 py-3 font-medium">Название</th>
            <th class="text-left px-4 py-3 font-medium">Slug</th>
            <th class="text-left px-4 py-3 font-medium">Активен</th>
            <th class="text-left px-4 py-3 font-medium">Порядок</th>
            <th class="text-right px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in partners" :key="p.id" class="border-t border-slate-50">
            <td class="px-4 py-3">
              <img
                v-if="p.logo_url"
                :src="resolveApiAsset(p.logo_url)"
                :alt="p.name"
                class="w-10 h-10 object-contain rounded bg-slate-50 border border-slate-100"
              />
              <div
                v-else
                class="w-10 h-10 rounded bg-slate-100 text-slate-300 flex items-center justify-center text-xs"
              >
                —
              </div>
            </td>
            <td class="px-4 py-3 font-medium">{{ p.name }}</td>
            <td class="px-4 py-3 text-slate-500">{{ p.slug }}</td>
            <td class="px-4 py-3">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  :checked="p.is_active"
                  @change="toggleActive(p)"
                  class="sr-only peer"
                />
                <span
                  class="w-9 h-5 rounded-full bg-slate-200 peer-checked:bg-green-500 relative transition-colors"
                >
                  <span
                    class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform"
                    :class="p.is_active ? 'translate-x-4' : ''"
                  />
                </span>
              </label>
            </td>
            <td class="px-4 py-3 text-slate-500">{{ p.sort_order }}</td>
            <td class="px-4 py-3 text-right">
              <button
                @click="openEdit(p)"
                class="px-3 py-1 text-xs border border-slate-200 rounded-lg hover:bg-blue-50 text-slate-600 cursor-pointer mr-2"
              >
                Редактировать
              </button>
              <button
                @click="remove(p)"
                class="px-3 py-1 text-xs border border-red-200 rounded-lg hover:bg-red-50 text-red-500 cursor-pointer"
              >
                Удалить
              </button>
            </td>
          </tr>
          <tr v-if="!partners.length">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">
              Нет партнёров
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Модалка формы -->
    <div
      v-if="showForm"
      @click="onBackdrop"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-40 p-4"
    >
      <div
        class="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-auto"
      >
        <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 class="text-lg font-bold text-slate-800">
            {{ editingId ? 'Редактировать партнёра' : 'Новый партнёр' }}
          </h3>
          <button
            @click="closeForm"
            class="text-slate-400 hover:text-slate-600 cursor-pointer"
          >
            &times;
          </button>
        </div>

        <form @submit.prevent="save" class="p-6 space-y-4">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Название *</label>
            <input
              v-model="form.name"
              type="text"
              required
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <div>
            <label class="block text-xs text-slate-500 mb-1">
              Slug <span class="text-slate-400">(опционально, будет сгенерирован)</span>
            </label>
            <input
              v-model="form.slug"
              type="text"
              placeholder="my-partner"
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <div>
            <label class="block text-xs text-slate-500 mb-1">Логотип *</label>
            <div class="flex items-center gap-3">
              <div
                class="w-20 h-20 rounded-lg border border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden shrink-0"
              >
                <img
                  v-if="form.logo_url"
                  :src="resolveApiAsset(form.logo_url)"
                  alt="logo preview"
                  class="max-w-full max-h-full object-contain"
                />
                <span v-else class="text-xs text-slate-300">нет</span>
              </div>
              <div class="flex flex-col gap-2">
                <button
                  type="button"
                  @click="onPickFile"
                  :disabled="uploading"
                  class="px-3 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-blue-50 text-slate-700 cursor-pointer disabled:opacity-50"
                >
                  {{ uploading ? 'Загрузка...' : 'Выбрать файл' }}
                </button>
                <input
                  ref="fileInput"
                  type="file"
                  accept="image/*"
                  @change="onFileChange"
                  class="hidden"
                />
                <p v-if="form.logo_url" class="text-xs text-slate-400 break-all">
                  {{ form.logo_url }}
                </p>
              </div>
            </div>
          </div>

          <div>
            <label class="block text-xs text-slate-500 mb-1">Короткое описание</label>
            <input
              v-model="form.short_description"
              type="text"
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <div>
            <label class="block text-xs text-slate-500 mb-1">Полное описание</label>
            <textarea
              v-model="form.full_description"
              rows="5"
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-y"
            />
          </div>

          <div>
            <label class="block text-xs text-slate-500 mb-1">Ссылка на сайт</label>
            <input
              :value="form.website_url ?? ''"
              @input="form.website_url = ($event.target as HTMLInputElement).value || null"
              type="url"
              placeholder="https://example.com"
              class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs text-slate-500 mb-1">Порядок</label>
              <input
                v-model.number="form.sort_order"
                type="number"
                class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
            </div>
            <div class="flex items-end">
              <label class="inline-flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                <input v-model="form.is_active" type="checkbox" class="rounded" />
                Активен
              </label>
            </div>
          </div>

          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="closeForm"
              class="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 cursor-pointer"
            >
              Отмена
            </button>
            <button
              type="submit"
              :disabled="saving || uploading"
              class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 cursor-pointer"
            >
              {{ saving ? 'Сохранение...' : editingId ? 'Сохранить' : 'Создать' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
