import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },
    {
      path: '/invite',
      name: 'invite',
      component: () => import('@/views/InviteView.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AdminLayout.vue'),
      meta: { auth: true },
      children: [
        { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
        { path: 'clients', name: 'clients', component: () => import('@/views/ClientsView.vue') },
        { path: 'clients/:id', name: 'client-detail', component: () => import('@/views/ClientDetailView.vue') },
        { path: 'applications', name: 'applications', component: () => import('@/views/ApplicationsView.vue') },
        { path: 'team', name: 'team', component: () => import('@/views/TeamView.vue') },
        { path: 'bot-profiles', name: 'bot-profiles', component: () => import('@/views/BotProfilesView.vue') },
        { path: 'partners', name: 'partners', component: () => import('@/views/PartnersView.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('admin_token')
  if (to.meta.auth && !token) return '/login'
  if (to.meta.guest && token) return '/'
})

export default router
