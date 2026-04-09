<script setup lang="ts">
import type { Client } from '@/types'

defineProps<{
  client: Client
}>()

defineEmits<{
  sendReset: []
  deleteClient: []
}>()
</script>

<template>
  <div class="bg-white rounded-xl border border-slate-100 shadow-sm p-6 mb-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold text-slate-800">
        Клиент #{{ client.id }}
      </h2>
      <div class="flex gap-2">
        <button
          @click="$emit('sendReset')"
          class="px-3 py-1.5 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600 cursor-pointer"
        >
          Сбросить пароль
        </button>
        <button
          @click="$emit('deleteClient')"
          class="px-3 py-1.5 text-xs bg-red-500 text-white rounded-lg hover:bg-red-600 cursor-pointer"
        >
          Удалить
        </button>
      </div>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
      <div>
        <span class="text-slate-400">Email</span>
        <div class="font-medium">{{ client.email }}</div>
      </div>
      <div>
        <span class="text-slate-400">Имя</span>
        <div class="font-medium">{{ client.name || '—' }}</div>
      </div>
      <div>
        <span class="text-slate-400">Телефон</span>
        <div class="font-medium">{{ client.phone || '—' }}</div>
      </div>
      <div>
        <span class="text-slate-400">Telegram</span>
        <div class="font-medium">{{ client.telegram_username || '—' }}</div>
      </div>
      <div>
        <span class="text-slate-400">Баланс заявок</span>
        <div class="font-medium">{{ client.applications_balance }}</div>
      </div>
      <div>
        <span class="text-slate-400">Регистрация</span>
        <div class="font-medium">
          {{ new Date(client.created_at).toLocaleDateString('ru') }}
        </div>
      </div>
    </div>
  </div>
</template>
