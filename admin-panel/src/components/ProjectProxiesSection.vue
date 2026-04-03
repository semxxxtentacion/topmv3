<script setup lang="ts">
import type { ProjectProxy } from '@/types'

defineProps<{
  proxies: ProjectProxy[]
  proxyFormVisible: boolean
  proxyFormUrl: string
  editingProxyId: number | null
  proxySaving: boolean
  proxyCheckStatus: Record<number, 'loading' | 'ok' | 'error'>
  proxyCheckIp: Record<number, string>
  proxyCheckError: Record<number, string>
  appId: number
}>()

defineEmits<{
  add: []
  edit: [proxy: ProjectProxy]
  delete: [proxyId: number]
  save: []
  cancel: []
  'update:proxyFormUrl': [value: string]
}>()
</script>

<template>
  <div class="mt-3">
    <div class="flex items-center justify-between mb-2">
      <h5 class="text-xs font-bold text-slate-500">
        Прокси
        <span class="text-slate-400 font-normal">({{ proxies.length }})</span>
      </h5>
      <button
        @click="$emit('add')"
        class="px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded hover:bg-slate-200 cursor-pointer"
      >
        + Добавить
      </button>
    </div>

    <!-- Proxy form -->
    <div
      v-if="proxyFormVisible"
      class="flex gap-2 items-center mb-2"
    >
      <input
        :value="proxyFormUrl"
        @input="$emit('update:proxyFormUrl', ($event.target as HTMLInputElement).value)"
        placeholder="socks5://login:pass@server:port"
        class="flex-1 px-3 py-1.5 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-300"
      />
      <button
        @click="$emit('save')"
        :disabled="!proxyFormUrl.trim() || proxySaving"
        class="px-3 py-1.5 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 cursor-pointer"
      >
        {{ proxySaving ? 'Сохранение...' : (editingProxyId ? 'Обновить' : 'Добавить') }}
      </button>
      <button
        @click="$emit('cancel')"
        class="px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-100 cursor-pointer"
      >
        Отмена
      </button>
    </div>

    <!-- Proxy list -->
    <div v-if="proxies.length" class="space-y-1">
      <div
        v-for="p in proxies"
        :key="p.id"
        class="bg-slate-50 rounded px-3 py-1.5 text-xs"
      >
        <div class="flex items-center gap-2">
          <!-- Status dot -->
          <span
            v-if="proxyCheckStatus[p.id] === 'ok'"
            class="shrink-0 w-2 h-2 rounded-full bg-green-500"
            title="Работает"
          />
          <span
            v-else-if="proxyCheckStatus[p.id] === 'error'"
            class="shrink-0 w-2 h-2 rounded-full bg-red-500"
            title="Не работает"
          />
          <span
            v-else-if="proxyCheckStatus[p.id] === 'loading'"
            class="shrink-0 w-2 h-2 rounded-full bg-amber-400 animate-pulse"
            title="Проверка..."
          />
          <span
            v-else
            class="shrink-0 w-2 h-2 rounded-full bg-slate-300"
            title="Не проверен"
          />

          <span class="font-mono text-slate-600 truncate min-w-0">{{ p.proxy_url }}</span>

          <span
            v-if="proxyCheckStatus[p.id] === 'ok'"
            class="shrink-0 text-green-600 font-medium"
          >
            {{ proxyCheckIp[p.id] }}
          </span>

          <div class="flex gap-1 shrink-0 ml-auto">
          <button
            @click="$emit('edit', p)"
            class="px-2 py-0.5 text-slate-400 hover:text-blue-500 cursor-pointer"
          >
            Изм.
          </button>
          <button
            @click="$emit('delete', p.id)"
            class="px-2 py-0.5 text-slate-400 hover:text-red-500 cursor-pointer"
          >
            Удалить
          </button>
          </div>
        </div>
        <div
          v-if="proxyCheckStatus[p.id] === 'error' && proxyCheckError[p.id]"
          class="mt-1 text-red-500 pl-4"
        >
          {{ proxyCheckError[p.id] }}
        </div>
      </div>
    </div>
    <div v-else-if="!proxyFormVisible" class="text-xs text-slate-400">
      Нет прокси
    </div>
  </div>
</template>
