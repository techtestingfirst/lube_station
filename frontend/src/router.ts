import { createRouter, createWebHistory } from 'vue-router'
import { bootUser } from './api'

const routes = [
  { path: '/login', component: () => import('./pages/Login.vue') },
  { path: '/', component: () => import('./pages/Dashboard.vue') },
  { path: '/store', component: () => import('./pages/Store.vue') },
  { path: '/checkout/:plan', component: () => import('./pages/Checkout.vue') },
  { path: '/cart', component: () => import('./pages/Cart.vue') },
  { path: '/invoices', component: () => import('./pages/Invoices.vue') },
  { path: '/pay/:invoice', component: () => import('./pages/Payment.vue') },
  { path: '/services', component: () => import('./pages/Services.vue') },
  { path: '/vps', component: () => import('./pages/Vps.vue') },
  { path: '/dedicated', component: () => import('./pages/Dedicated.vue') },
  { path: '/domains', component: () => import('./pages/Domains.vue') },
  { path: '/dns/:domain', component: () => import('./pages/Dns.vue') },
  { path: '/downloads', component: () => import('./pages/Downloads.vue') },
  { path: '/support', component: () => import('./pages/Support.vue') },
  { path: '/account', component: () => import('./pages/Account.vue') },
  { path: '/:path(.*)*', component: () => import('./pages/NotFound.vue') },
]

export const router = createRouter({
  history: createWebHistory('/lube_station'),
  routes,
})

const PUBLIC = ['/login', '/store']

router.beforeEach((to) => {
  if (PUBLIC.includes(to.path)) return true
  const user = bootUser()
  if (!user || user === 'Guest') {
    if (to.path !== '/login') return '/login'
  }
  return true
})
