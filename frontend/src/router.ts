import { createRouter, createWebHistory } from 'vue-router'
import { bootUser, sessionUser } from './api'

const routes = [
  { path: '/login', component: () => import('./pages/Login.vue') },
  { path: '/signup', component: () => import('./pages/Signup.vue') },
  { path: '/forgot', component: () => import('./pages/Forgot.vue') },
  { path: '/reset', component: () => import('./pages/Reset.vue') },
  { path: '/', component: () => import('./pages/Dashboard.vue') },
  { path: '/store', component: () => import('./pages/Store.vue') },
  { path: '/checkout/:plan', component: () => import('./pages/Checkout.vue') },
  { path: '/domain/:cart/:row', component: () => import('./pages/Domain.vue') },
  { path: '/domain/:row', component: () => import('./pages/Domain.vue') },
  { path: '/cart', component: () => import('./pages/Cart.vue') },
  { path: '/order/:order', component: () => import('./pages/OrderDetail.vue') },
  { path: '/orders', component: () => import('./pages/Orders.vue') },
  { path: '/invoices', component: () => import('./pages/Invoices.vue') },
  { path: '/invoice/:invoice', component: () => import('./pages/InvoiceDetail.vue') },
  { path: '/pay/:invoice', component: () => import('./pages/Payment.vue') },
  { path: '/services', component: () => import('./pages/Services.vue') },
  { path: '/service/:service', component: () => import('./pages/ServiceDetail.vue') },
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
  history: createWebHistory('/store'),
  routes,
})

const PUBLIC = ['/login', '/signup', '/forgot', '/reset', '/store']

router.beforeEach(async (to) => {
  if (PUBLIC.includes(to.path)) {
    // Logged-in users don't need auth pages (dev server has no boot data).
    if (['/login', '/signup'].includes(to.path) && !bootUser() && (await sessionUser())) return '/'
    return true
  }
  const user = bootUser() || (await sessionUser())
  if (!user) {
    if (to.path !== '/login') return '/login'
  }
  return true
})
