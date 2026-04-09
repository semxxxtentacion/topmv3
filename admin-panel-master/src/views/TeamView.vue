<script setup lang="ts">
import { useTeam } from '@/composables/useTeam'
import { roleLabel, roleClass } from '@/utils/formatters'

const {
  auth, team, loading,
  showInvite, inviteEmail, inviteRole, inviteLoading, inviteMsg, inviteErr,
  canInvite,
  sendInvite, deactivate,
} = useTeam()
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-slate-800">Команда</h2>
      <button
        v-if="canInvite"
        @click="showInvite = !showInvite"
        class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 cursor-pointer"
      >
        Пригласить
      </button>
    </div>

    <!-- Invite form -->
    <div v-if="showInvite" class="bg-white rounded-xl border border-slate-100 shadow-sm p-5 mb-6">
      <h3 class="text-sm font-bold text-slate-700 mb-3">Отправить приглашение</h3>
      <form @submit.prevent="sendInvite" class="flex gap-3 items-end flex-wrap">
        <div class="flex-1 min-w-48">
          <label class="block text-xs text-slate-500 mb-1">Email</label>
          <input
            v-model="inviteEmail"
            type="email"
            required
            class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
        <div>
          <label class="block text-xs text-slate-500 mb-1">Роль</label>
          <select
            v-model="inviteRole"
            class="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          >
            <option value="manager">Менеджер</option>
            <option v-if="auth.role === 'superadmin'" value="admin">Админ</option>
          </select>
        </div>
        <button
          type="submit"
          :disabled="inviteLoading"
          class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 cursor-pointer"
        >
          Отправить
        </button>
      </form>
      <p v-if="inviteMsg" class="text-sm text-green-600 mt-2">{{ inviteMsg }}</p>
      <p v-if="inviteErr" class="text-sm text-red-500 mt-2">{{ inviteErr }}</p>
    </div>

    <!-- Team table -->
    <div class="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500">
          <tr>
            <th class="text-left px-4 py-3 font-medium">Имя</th>
            <th class="text-left px-4 py-3 font-medium">Email</th>
            <th class="text-left px-4 py-3 font-medium">Роль</th>
            <th class="text-left px-4 py-3 font-medium">Статус</th>
            <th class="text-left px-4 py-3 font-medium">Дата</th>
            <th class="text-left px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in team" :key="m.id" class="border-t border-slate-50">
            <td class="px-4 py-3 font-medium">{{ m.name }}</td>
            <td class="px-4 py-3">{{ m.email }}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="roleClass(m.role)">
                {{ roleLabel(m.role) }}
              </span>
            </td>
            <td class="px-4 py-3">
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="m.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
              >
                {{ m.is_active ? 'Активен' : 'Деактивирован' }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-400">{{ new Date(m.created_at).toLocaleDateString('ru') }}</td>
            <td class="px-4 py-3">
              <button
                v-if="m.is_active && String(m.id) !== auth.role && canInvite"
                @click="deactivate(m.id)"
                class="text-xs text-red-500 hover:underline cursor-pointer"
              >
                Деактивировать
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
