<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { statusLabel, statusClass } from '@/utils/formatters'
import { useClientDetail } from '@/composables/useClientDetail'
import { useBotTasks } from '@/composables/useBotTasks'
import { useProjectProxies } from '@/composables/useProjectProxies'
import { useNotify } from '@/composables/useNotify'
import ClientInfoCard from '@/components/ClientInfoCard.vue'
import ProjectEditForm from '@/components/ProjectEditForm.vue'
import ProjectProxiesSection from '@/components/ProjectProxiesSection.vue'
import BotTasksSection from '@/components/BotTasksSection.vue'
import BotTaskNewForm from '@/components/BotTaskNewForm.vue'
import PaymentsTable from '@/components/PaymentsTable.vue'

const route = useRoute()
const clientId = Number(route.params.id)

const {
  client, applications, payments, loading,
  cities, citySearch, sortedCities,
  editingId, editForm, editSaving,
  loadClient, deleteClient, deleteApplication, sendReset, startEdit, selectCity, saveEdit,
} = useClientDetail(clientId)

const {
  botTasks, botTasksLoading,
  showNewTaskForm, newTaskForm,
  loadBotTasks,
  openNewTaskForm, createBotTask, togglePause, deleteTask,
} = useBotTasks()

const {
  proxies,
  proxyFormVisible,
  proxyFormUrl,
  editingProxyId,
  proxySaving,
  proxyCheckStatus,
  proxyCheckIp,
  proxyCheckError,
  loadProxies,
  openProxyForm,
  startEditProxy,
  cancelProxyForm,
  saveProxy,
  checkAllProxies,
  deleteProxy,
} = useProjectProxies()

const { notify } = useNotify()

function copyText(text: string) {
  navigator.clipboard.writeText(text.trim())
  notify('Скопировано', 'info', 1500)
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let proxyPollTimer: ReturnType<typeof setInterval> | null = null
const appIds = ref<number[]>([])

onMounted(async () => {
  const apps = await loadClient()
  if (apps) {
    appIds.value = apps.map((a) => a.id)
    for (const id of appIds.value) {
      loadBotTasks(id)
      loadProxies(id)
    }
    // Проверяем все прокси после загрузки (даём время на loadProxies)
    setTimeout(() => checkAllProxies(appIds.value), 500)

    pollTimer = setInterval(() => {
      for (const id of appIds.value) {
        loadBotTasks(id, true)
      }
    }, 20000)

    // Проверка прокси каждую минуту
    proxyPollTimer = setInterval(() => {
      checkAllProxies(appIds.value)
    }, 60000)
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (proxyPollTimer) clearInterval(proxyPollTimer)
})
</script>

<template>
  <div>
    <RouterLink
      to="/clients"
      class="text-sm text-blue-500 hover:underline mb-4 inline-block"
    >
      &larr; Все клиенты
    </RouterLink>

    <div v-if="loading" class="text-sm text-slate-400">Загрузка...</div>

    <template v-else-if="client">
      <ClientInfoCard
        :client="client"
        @send-reset="sendReset"
        @delete-client="deleteClient"
      />

      <!-- Applications / Projects -->
      <div class="bg-white rounded-xl border border-slate-100 shadow-sm p-6 mb-6">
        <h3 class="text-md font-bold text-slate-800 mb-3">
          Проекты
          <span class="text-slate-400 font-normal">({{ applications.length }})</span>
        </h3>
        <div v-if="!applications.length" class="text-sm text-slate-400">
          Нет проектов
        </div>

        <div
          v-for="a in applications"
          :key="a.id"
          class="border-t border-slate-100 py-4 first:border-0 first:pt-0"
        >
          <!-- Project row -->
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-4 text-sm">
              <span class="text-slate-400">#{{ a.id }}</span>
              <span class="font-medium">{{ a.site }}</span>
              <span class="text-slate-400">{{ a.region || '—' }}</span>
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="statusClass(a.status)"
              >
                {{ statusLabel(a.status) }}
              </span>
              <span class="text-slate-400 text-xs">{{ a.manager_name || '' }}</span>
            </div>
            <div class="flex gap-2">
              <button
                @click="startEdit(a)"
                class="px-3 py-1 text-xs border border-slate-200 rounded-lg hover:bg-blue-50 text-slate-600 cursor-pointer"
              >
                {{ editingId === a.id ? 'Свернуть' : 'Редактировать' }}
              </button>
              <button
                @click="deleteApplication(a.id)"
                class="px-3 py-1 text-xs border border-red-200 rounded-lg hover:bg-red-50 text-red-500 cursor-pointer"
              >
                Удалить
              </button>
            </div>
          </div>

          <!-- Inline details -->
          <div class="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
            <span v-if="a.google">Google</span>
            <span v-if="a.yandex">Yandex</span>
            <span v-if="a.audit">Аудит</span>
            <span v-if="a.keywords_selection">Подбор слов</span>
            <span>{{ new Date(a.created_at).toLocaleDateString('ru') }}</span>
          </div>

          <!-- Keywords preview -->
          <div
            v-if="a.keywords && editingId !== a.id"
            class="mt-2 text-sm text-slate-500 bg-slate-50 rounded p-3 max-h-48 overflow-auto space-y-0.5"
          >
            <div
              v-for="(kw, idx) in a.keywords.split('\n').filter((k: string) => k.trim())"
              :key="idx"
              class="flex items-center gap-1 group"
            >
              <span>{{ kw }}</span>
              <button
                @click="copyText(kw)"
                class="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-blue-500 transition-opacity cursor-pointer"
                title="Копировать"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Edit form -->
          <ProjectEditForm
            v-if="editingId === a.id"
            :edit-form="editForm"
            :edit-saving="editSaving"
            :city-search="citySearch"
            :sorted-cities="sortedCities"
            :cities="cities"
            @save="saveEdit(a.id)"
            @cancel="editingId = null"
            @select-city="selectCity"
            @update:city-search="citySearch = $event"
          />

          <!-- Project Proxies -->
          <ProjectProxiesSection
            :proxies="proxies[a.id] || []"
            :proxy-form-visible="proxyFormVisible === a.id"
            :proxy-form-url="proxyFormUrl"
            :editing-proxy-id="editingProxyId"
            :proxy-saving="proxySaving"
            :proxy-check-status="proxyCheckStatus"
            :proxy-check-ip="proxyCheckIp"
            :proxy-check-error="proxyCheckError"
            :app-id="a.id"
            @add="openProxyForm(a.id)"
            @edit="startEditProxy"
            @delete="deleteProxy(a.id, $event)"
            @save="saveProxy(a.id)"
            @cancel="cancelProxyForm"
            @update:proxy-form-url="proxyFormUrl = $event"
          />

          <!-- Bot Tasks -->
          <BotTasksSection
            :tasks="botTasks[a.id] || []"
            :loading="botTasksLoading[a.id] || false"
            @add-task="openNewTaskForm(a.id, a)"
            @toggle-pause="togglePause(a.id, $event)"
            @delete-task="deleteTask(a.id, $event)"
          >
            <BotTaskNewForm
              v-if="showNewTaskForm === a.id"
              :app-id="a.id"
              :new-task-form="newTaskForm"
              @create-task="createBotTask"
              @cancel="showNewTaskForm = null"
            />
          </BotTasksSection>
        </div>
      </div>

      <PaymentsTable :payments="payments" />
    </template>
  </div>
</template>
