<script setup lang="ts">
import type { Payment } from '@/types'
import { formatMoney } from '@/utils/formatters'

defineProps<{
  payments: Payment[]
}>()
</script>

<template>
  <div class="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
    <h3 class="text-md font-bold text-slate-800 mb-3">
      Платежи
      <span class="text-slate-400 font-normal">({{ payments.length }})</span>
    </h3>
    <div v-if="!payments.length" class="text-sm text-slate-400">
      Нет платежей
    </div>
    <table v-else class="w-full text-sm">
      <thead class="text-slate-500">
        <tr>
          <th class="text-left py-2">ID</th>
          <th class="text-left py-2">Тариф</th>
          <th class="text-left py-2">Сумма</th>
          <th class="text-left py-2">Статус</th>
          <th class="text-left py-2">Дата</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="p in payments"
          :key="p.id"
          class="border-t border-slate-50"
        >
          <td class="py-2 text-slate-400">#{{ p.payment_id }}</td>
          <td class="py-2">{{ p.tariff }}</td>
          <td class="py-2">{{ formatMoney(p.amount) }}</td>
          <td class="py-2">
            <span
              class="px-2 py-0.5 rounded-full text-xs font-medium"
              :class="
                p.status === 'CONFIRMED'
                  ? 'bg-green-100 text-green-700'
                  : 'bg-slate-100 text-slate-500'
              "
            >
              {{ p.status }}
            </span>
          </td>
          <td class="py-2 text-slate-400">
            {{ new Date(p.created_at).toLocaleDateString('ru') }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
