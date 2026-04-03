import { ref, computed } from 'vue'

export function usePagination(limit = 25) {
  const page = ref(0)
  const total = ref(0)

  const hasPages = computed(() => total.value > limit)
  const hasPrev = computed(() => page.value > 0)
  const hasNext = computed(() => (page.value + 1) * limit < total.value)
  const totalPages = computed(() => Math.ceil(total.value / limit))
  const offset = computed(() => page.value * limit)

  function prev() {
    if (hasPrev.value) page.value--
  }

  function next() {
    if (hasNext.value) page.value++
  }

  function reset() {
    page.value = 0
  }

  return { page, total, limit, hasPages, hasPrev, hasNext, totalPages, offset, prev, next, reset }
}
