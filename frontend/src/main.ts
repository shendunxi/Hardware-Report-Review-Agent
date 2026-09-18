import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { createApplicationRouter } from './router'
import './styles.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(createApplicationRouter(pinia))
app.mount('#app')
