<template>
  <div class="main-shell">
    <n-layout has-sider class="app-frame">
      <n-layout-sider
        bordered
        show-trigger
        class="app-sider"
        :collapsed-width="72"
        :width="236"
        :collapsed="appStore.sidebarCollapsed"
        @collapse="appStore.setSidebarCollapsed(true)"
        @expand="appStore.setSidebarCollapsed(false)"
      >
        <div class="logo">
          <div class="logo-mark">AI</div>
          <div v-if="!appStore.sidebarCollapsed" class="logo-copy">
            <h2>AI Writer</h2>
            <p>Knowledge-first workspace</p>
          </div>
        </div>

        <n-menu
          class="app-menu"
          :collapsed="appStore.sidebarCollapsed"
          :collapsed-width="72"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="currentRoute"
          @update:value="handleMenuSelect"
        />

        <div class="sider-footer">
          <n-tooltip placement="right" :disabled="!appStore.sidebarCollapsed">
            <template #trigger>
              <n-button text size="large" class="theme-switch" @click="appStore.toggleTheme">
                <template #icon>
                  <n-icon>
                    <SunnyOutline v-if="appStore.isDark" />
                    <MoonOutline v-else />
                  </n-icon>
                </template>
                <span v-if="!appStore.sidebarCollapsed">
                  {{ appStore.isDark ? '切换浅色' : '切换深色' }}
                </span>
              </n-button>
            </template>
            切换主题
          </n-tooltip>
        </div>
      </n-layout-sider>

      <n-layout class="app-content-layout">
        <n-layout-header class="app-header" bordered>
          <div class="header-main">
            <div class="header-copy">
              <span class="header-kicker">WORKSPACE</span>
            </div>

            <n-space align="center" class="header-actions">
              <template v-if="token">
                <n-dropdown :options="userOptions" @select="handleUserSelect">
                  <n-button quaternary class="user-trigger">
                    <template #icon>
                      <n-icon><PersonOutline /></n-icon>
                    </template>
                    {{ username || '加载中...' }}
                  </n-button>
                </n-dropdown>
              </template>
              <template v-else>
                <n-button quaternary @click="router.push('/login')">登录</n-button>
                <n-button type="primary" @click="router.push('/register')">注册</n-button>
              </template>
            </n-space>
          </div>
        </n-layout-header>

        <n-layout-content class="app-content" content-style="height: 100%; display: flex; flex-direction: column; padding: 24px;">
          <div class="route-view-shell">
            <router-view />
          </div>
        </n-layout-content>
      </n-layout>
    </n-layout>
  </div>
</template>

<script setup lang="ts">
import { computed, h, Component, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NIcon, useDialog } from 'naive-ui'
import type { MenuOption, DropdownOption } from 'naive-ui'
import {
  FolderOpenOutline as FolderIcon,
  DocumentTextOutline as DocIcon,
  HomeOutline as HomeIcon,
  SunnyOutline,
  MoonOutline,
  PersonOutline,
  LogOutOutline,
} from '@vicons/ionicons5'
import { useAppStore } from '@/stores/app'
import { authApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const dialog = useDialog()

const username = ref('')
const token = ref(localStorage.getItem('token'))

onMounted(async () => {
  if (token.value) {
    try {
      const user: any = await authApi.getCurrentUser()
      username.value = user.username
    } catch {
      token.value = null
      localStorage.removeItem('token')
    }
  }
})

const currentRoute = computed(() => route.name as string)

const renderIcon = (icon: Component) => {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions: MenuOption[] = [
  {
    label: '首页',
    key: 'Home',
    icon: renderIcon(HomeIcon),
  },
  {
    label: '知识库管理',
    key: 'Knowledge',
    icon: renderIcon(FolderIcon),
  },
  {
    label: '知识写作',
    key: 'OpenWps',
    icon: renderIcon(DocIcon),
  },
  {
    label: '长文生成',
    key: 'Document',
    icon: renderIcon(DocIcon),
  },
]

const userOptions: DropdownOption[] = [
  {
    label: '退出登录',
    key: 'logout',
    icon: renderIcon(LogOutOutline),
  },
]

function handleMenuSelect(key: string) {
  router.push({ name: key })
}

function handleUserSelect(key: string) {
  if (key === 'logout') {
    dialog.warning({
      title: '确认退出',
      content: '确定要退出当前账号吗？',
      positiveText: '确定',
      negativeText: '取消',
      onPositiveClick: () => {
        localStorage.removeItem('token')
        router.push('/login')
      },
    })
  }
}
</script>

<style scoped>
.main-shell {
  height: 100vh;
  padding: 0;
}

.app-frame {
  height: 100%;
  overflow: hidden;
  background: transparent;
}

.app-sider {
  position: relative;
  background: transparent;
}

.app-sider :deep(.n-layout-sider__border) {
  background-color: transparent;
}

.app-sider :deep(.n-layout-toggle-button) {
  border-radius: 14px 0 0 14px;
  border-color: transparent;
  background: transparent;
}

.logo {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 88px;
  padding: 18px 20px;
  border-bottom: none;
}

.logo-mark {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--aw-paper-strong);
  border: 1px solid var(--aw-border);
  color: var(--aw-accent);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.logo-copy h2 {
  margin: 0;
  font-size: 1.55rem;
  color: var(--aw-text);
}

.logo-copy p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--aw-text-muted);
}

.app-menu {
  padding: 14px 12px 96px;
}

.app-menu :deep(.n-menu-item-content) {
  border-radius: 16px;
  min-height: 46px;
}

.app-menu :deep(.n-menu-item-content-header) {
  font-weight: 600;
}

.sider-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 18px;
  padding: 0 12px;
}

.theme-switch {
  width: 100%;
  justify-content: flex-start;
  border-radius: 16px;
  padding: 12px 14px;
  border: 1px solid var(--aw-border);
  background: var(--aw-paper-strong);
}

.app-content-layout {
  background: transparent;
}

.app-header {
  height: 64px;
  padding: 0 24px;
  background: transparent;
}

.header-main {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.header-copy {
  display: flex;
  align-items: center;
}

.header-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--aw-text-muted);
}

.header-actions {
  flex-wrap: wrap;
}

.user-trigger {
  min-width: 124px;
}

.app-content {
  height: calc(100vh - 100px);
  background: transparent;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.route-view-shell {
  width: 100%;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

@media (max-width: 900px) {
  .main-shell {
    padding: 10px;
  }

  .app-header {
    height: auto;
    padding: 16px 18px;
  }

  .header-main {
    align-items: flex-start;
    flex-direction: column;
  }

  .app-content {
    height: calc(100vh - 150px);
  }
}
</style>
