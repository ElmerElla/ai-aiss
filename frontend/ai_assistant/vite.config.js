/**
 * Vite 构建配置文件
 *
 * 功能介绍：
 * · 使用 @vitejs/plugin-vue 支持 Vue 3 单文件组件编译
 * · 配置路径别名 @ 指向 src 目录
 * · 开发服务器监听 127.0.0.1:6001
 * · 配置代理规则：/api 请求转发到后端 http://localhost:8000
 */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    host: '127.0.0.1',
    port: 6001,
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // 修改为 HTTP
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, '') // 如果后端不需要 /api 前缀，请取消注释此行
      }
    }
  }
})