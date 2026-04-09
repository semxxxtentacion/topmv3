<script setup lang="ts">
import { useNotify } from '@/composables/useNotify'

const { notifications } = useNotify()
</script>

<template>
  <div class="fixed top-4 right-4 z-50 space-y-2">
    <TransitionGroup name="toast">
      <div
        v-for="n in notifications"
        :key="n.id"
        class="flex overflow-hidden rounded-lg shadow-lg min-w-48 max-w-80"
      >
        <!-- Color stripe -->
        <div
          class="w-3 shrink-0"
          :class="{
            'bg-green-500': n.type === 'success',
            'bg-red-500': n.type === 'error',
            'bg-blue-400': n.type === 'info',
          }"
        />
        <!-- Content -->
        <div class="px-4 py-2.5 bg-slate-800 text-white text-sm font-medium flex-1">
          {{ n.message }}
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease-out;
}
.toast-leave-active {
  transition: all 0.2s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(40px);
}
</style>
