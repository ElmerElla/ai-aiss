/**
 * 应用入口模块
 *
 * 功能介绍：
 * -----------
 * 本模块是 Vue 3 应用的初始化入口，负责：
 * 1. 创建 Vue 应用实例
 * 2. 挂载 Pinia 状态管理
 * 3. 挂载 Vue Router 路由
 * 4. 导入全局样式
 * 5. 挂载到 DOM 的 #app 节点
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './styles/global.css'

// 创建 Vue 应用实例
const app = createApp(App)

// 挂载 Pinia 状态管理
app.use(createPinia())

// 挂载路由系统
app.use(router)

// 挂载到 DOM
app.mount('#app')