import { ref } from 'vue'

interface Notification {
  id: number
  message: string
  type: 'success' | 'error' | 'info'
}

const notifications = ref<Notification[]>([])
let nextId = 0

export function useNotify() {
  function notify(message: string, type: Notification['type'] = 'success', duration = 3000) {
    const id = nextId++
    notifications.value.push({ id, message, type })
    setTimeout(() => {
      notifications.value = notifications.value.filter((n) => n.id !== id)
    }, duration)
  }

  return { notifications, notify }
}
