import { ref } from 'vue'
import api from '@/api/client'
import { useNotify } from '@/composables/useNotify'
import type { Application, BotTask } from '@/types'

export function useBotTasks() {
  const { notify } = useNotify()
  const botTasks = ref<Record<number, BotTask[]>>({})
  const botTasksLoading = ref<Record<number, boolean>>({})

  // New task form
  const showNewTaskForm = ref<number | null>(null)
  const newTaskForm = ref({
    target_site: '',
    keyword: '',
    daily_visit_target: null as number | null,
    total_visit_target: null as number | null,
  })

  async function loadBotTasks(appId: number, silent = false) {
    if (!silent) botTasksLoading.value[appId] = true
    try {
      const { data } = await api.get(`/applications/${appId}/bot-tasks`)
      botTasks.value[appId] = data.items
    } catch {
      if (!silent) botTasks.value[appId] = []
    } finally {
      if (!silent) botTasksLoading.value[appId] = false
    }
  }

  function openNewTaskForm(appId: number, app: Application) {
    showNewTaskForm.value = appId
    newTaskForm.value = {
      target_site: app.site || '',
      keyword: '',
      daily_visit_target: null as number | null,
      total_visit_target: null as number | null,
    }
  }

  async function createBotTask(appId: number, formData?: { target_site: string; keyword: string; daily_visit_target: number | null; total_visit_target: number | null }) {
    const form = formData || newTaskForm.value
    if (!form.target_site || !form.keyword || !form.daily_visit_target || !form.total_visit_target) {
      notify('Заполните все обязательные поля', 'error')
      return
    }
    try {
      const { data } = await api.post(
        `/applications/${appId}/bot-tasks`,
        form,
      )
      if (!botTasks.value[appId]) botTasks.value[appId] = []
      botTasks.value[appId].unshift(data)
      showNewTaskForm.value = null
      notify('Задача создана', 'success')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      notify(err?.response?.data?.detail || 'Ошибка создания задачи', 'error')
    }
  }

  async function togglePause(appId: number, task: BotTask) {
    const { data } = await api.patch(`/bot-tasks/${task.id}/pause`, {
      is_paused: !task.is_paused,
    })
    const tasks = botTasks.value[appId]
    if (!tasks) return
    const idx = tasks.findIndex((t) => t.id === task.id)
    if (idx !== -1) {
      tasks[idx] = data
    }
    notify(data.is_paused ? 'Задача на паузе' : 'Задача запущена', 'info')
  }

  async function deleteTask(appId: number, taskId: number) {
    if (!confirm('Удалить задачу бота?')) return
    await api.delete(`/bot-tasks/${taskId}`)
    botTasks.value[appId] = (botTasks.value[appId] || []).filter(
      (t) => t.id !== taskId,
    )
    notify('Задача удалена', 'success')
  }

  return {
    botTasks, botTasksLoading,
    showNewTaskForm, newTaskForm,
    loadBotTasks,
    openNewTaskForm, createBotTask, togglePause, deleteTask,
  }
}
