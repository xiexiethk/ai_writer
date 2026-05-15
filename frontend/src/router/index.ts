import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import HomeView from '@/views/HomeView.vue'
import KnowledgeView from '@/views/KnowledgeView.vue'
import DocumentPreview from '@/views/DocumentPreview.vue'
import DocumentView from '@/views/DocumentView.vue'
import LoginView from '@/views/LoginView.vue'
import RegisterView from '@/views/RegisterView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { title: '登录', public: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterView,
    meta: { title: '注册', public: true },
  },
  // 首页 - 独立显示，不带侧边栏
  {
    path: '/',
    name: 'Home',
    component: HomeView,
    meta: { title: '首页' },
  },
  // 其他页面 - 使用 MainLayout（带侧边栏）
  {
    path: '/',
    component: MainLayout,
    children: [
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: KnowledgeView,
        meta: { title: '知识库管理', icon: 'database', protected: true },
      },
      {
        path: 'workspace-agent',
        name: 'OpenWps',
        component: () => import('@/views/OpenWpsHostView.vue'),
        meta: { title: '知识写作', icon: 'document', protected: true },
      },
      {
        path: 'chat',
        redirect: { name: 'OpenWps' },
      },
      {
        path: 'chat/:id',
        redirect: { name: 'OpenWps' },
      },
      {
        path: 'document',
        name: 'Document',
        component: DocumentView,
        meta: { title: '长文生成', icon: 'document', protected: true },
      },
    ],
  },
  {
    path: '/document/:id',
    name: 'DocumentPreview',
    component: DocumentPreview,
    meta: { title: '文档预览' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：检查登录状态
router.beforeEach((to) => {
  const token = window.localStorage.getItem('token')

  // 只有明确标记为受保护的页面才强制跳转
  // 首页 (Home) 现在是公开的
  if (to.meta.protected && !token) {
    return '/login'
  }

  return true
})

export default router
