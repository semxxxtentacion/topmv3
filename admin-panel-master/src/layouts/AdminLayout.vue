<script setup lang="ts">
import { RouterView, RouterLink, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { onMounted } from 'vue'
import NotificationToast from '@/components/NotificationToast.vue'

const auth = useAuthStore()
const route = useRoute()

onMounted(() => {
  if (auth.isAuth && !auth.name) {
    auth.fetchMe()
  }
})

const nav = [
  { to: '/', label: 'Дашборд', icon: '📊' },
  { to: '/applications', label: 'Заявки', icon: '📋' },
  { to: '/clients', label: 'Клиенты', icon: '👥' },
  { to: '/team', label: 'Команда', icon: '🛡️' },
  { to: '/bot-profiles', label: 'Профили бота', icon: '🤖' },
  { to: '/partners', label: 'Партнёры', icon: '🤝' },
]
</script>

<template>
  <div class="flex h-screen">
    <!-- Sidebar -->
    <aside class="w-60 flex flex-col border-r border-blue-100" style="background: var(--sidebar-bg)">
      <div class="p-5 border-b border-blue-100">
        <h1 class="text-lg font-bold text-blue-600">Топмашина</h1>
        <p class="text-xs text-slate-400 mt-0.5">Админ-панель</p>
      </div>

      <nav class="flex-1 p-3 space-y-1">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors"
          :class="
            (item.to === '/' ? route.path === '/' : route.path.startsWith(item.to))
              ? 'bg-blue-100 text-blue-700'
              : 'text-slate-600 hover:bg-blue-50 hover:text-blue-600'
          "
        >
          <span>{{ item.icon }}</span>
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="p-4 border-t border-blue-100">
        <div class="text-sm font-medium text-slate-700">{{ auth.name }}</div>
        <div class="text-xs text-slate-400">{{ auth.role }}</div>
        <button
          @click="auth.logout()"
          class="mt-2 text-xs text-red-500 hover:text-red-600 cursor-pointer"
        >
          Выйти
        </button>
      </div>
    </aside>

    <!-- Content -->
    <main class="flex-1 overflow-auto p-6">
      <RouterView />
    </main>

    <NotificationToast />
  </div>
</template>
