import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

export default defineConfig({
  // `frontendRoute` is where the site serves the app. The plugin proxies the
  // bench while you develop, and builds into the app's public and www folders.
  // Payment website pages must also proxy, or gateway redirects 404 in dev.
  plugins: [
    frappeui({
      frontendRoute: '/store',
      frappeProxy: {
        // Legacy frappe.call posts website callbacks to root "/" — must proxy
        // or make_payment never reaches the bench in dev.
        source:
          '^/(desk|app|login|api|assets|files|private|message|razorpay_checkout|stripe_checkout|payment-success|payment-failed|payment-cancel)|^/$',
      },
    }),
    vue(),
  ],
})
