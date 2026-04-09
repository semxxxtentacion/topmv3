import type { BotTask } from '@/types'

export function formatMoney(kopecks: number): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(kopecks / 100)
}

export function statusLabel(s: string | null): string {
  if (!s) return 'Ожидает'
  return s === 'accepted' ? 'Принята' : 'Отклонена'
}

export function statusClass(s: string | null): string {
  if (!s) return 'bg-amber-100 text-amber-700'
  return s === 'accepted' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
}

export function taskStatusLabel(task: BotTask): string {
  if (task.is_paused) return 'Пауза'
  if (task.successful_visits === null) return 'Ожидание'
  return 'Работает'
}

export function taskStatusClass(task: BotTask): string {
  if (task.is_paused) return 'bg-slate-100 text-slate-600'
  if (task.successful_visits === null) return 'bg-amber-100 text-amber-700'
  return 'bg-green-100 text-green-700'
}

export function roleLabel(r: string): string {
  const map: Record<string, string> = { superadmin: 'Суперадмин', admin: 'Админ', manager: 'Менеджер' }
  return map[r] || r
}

export function roleClass(r: string): string {
  const map: Record<string, string> = {
    superadmin: 'bg-purple-100 text-purple-700',
    admin: 'bg-blue-100 text-blue-700',
    manager: 'bg-slate-100 text-slate-600',
  }
  return map[r] || ''
}
