<template>
  <div class="minimal-home">
    <div class="content">
      <h1 class="title">AI Writer</h1>
      <div class="links">
        <button class="nav-button" @click="navigateTo('/knowledge')">知识库管理</button>
        <button class="nav-button" @click="navigateTo('/workspace-agent')">知识写作</button>
        <button class="nav-button" @click="navigateTo('/document')">长文生成</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const token = ref(localStorage.getItem('token'))

const navigateTo = (path: string) => {
  if (!token.value) {
    router.push('/login')
  } else {
    router.push(path)
  }
}
</script>

<style scoped>
.minimal-home {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--aw-bg);
  font-family: var(--aw-font-ui);
}

.content {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 48px;
}

.title {
  font-family: var(--aw-font-display);
  font-size: 3rem;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--aw-text);
  margin: 0;
}

.links {
  display: flex;
  gap: 24px;
}

.nav-button {
  background: transparent;
  border: 1px solid var(--aw-border);
  color: var(--aw-text-soft);
  padding: 12px 32px;
  font-size: 1.1rem;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.nav-button:hover {
  background: var(--aw-paper);
  color: var(--aw-text);
  border-color: var(--aw-border-strong);
}
</style>
