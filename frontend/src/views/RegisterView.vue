<template>
  <div class="auth-shell">
    <div class="auth-ambient" />

    <div class="auth-frame">
      <section class="auth-card">
        <router-link to="/" class="back-link">返回首页</router-link>
        <h2>注册 AI Writer</h2>
        <p class="auth-subtitle">创建一个新的知识写作账号</p>

        <form @submit.prevent="handleRegister">
          <div class="form-group">
            <label>用户名</label>
            <input
              v-model="regForm.username"
              type="text"
              placeholder="请设置用户名"
              required
            />
          </div>

          <div class="form-group">
            <label>邮箱</label>
            <input
              v-model="regForm.email"
              type="email"
              placeholder="请输入电子邮箱"
              required
            />
          </div>

          <div class="form-group">
            <label>密码</label>
            <input
              v-model="regForm.password"
              type="password"
              placeholder="请设置密码"
              required
            />
          </div>

          <div class="form-group">
            <label>确认密码</label>
            <input
              v-model="regForm.confirmPassword"
              type="password"
              placeholder="请再次输入密码"
              required
            />
          </div>

          <div v-if="errorMsg" class="message-strip error-strip">
            {{ errorMsg }}
          </div>

          <div v-if="successMsg" class="message-strip success-strip">
            {{ successMsg }}
          </div>

          <button type="submit" :disabled="loading" class="submit-btn">
            {{ loading ? '注册中...' : '立即注册' }}
          </button>
        </form>

        <div class="footer-links">
          <span>已有账号？</span>
          <router-link to="/login">返回登录</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'

const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

const regForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const handleRegister = async () => {
  if (regForm.password !== regForm.confirmPassword) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }

  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''

  try {
    await authApi.register({
      username: regForm.username,
      email: regForm.email,
      password: regForm.password,
    })

    successMsg.value = '注册成功，正在跳转到登录页...'
    setTimeout(() => {
      router.push('/login')
    }, 1500)
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-shell {
  position: relative;
  min-height: 100vh;
  padding: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.auth-ambient {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 16% 18%, rgba(201, 111, 69, 0.13), transparent 22%),
    radial-gradient(circle at 86% 84%, rgba(83, 125, 98, 0.11), transparent 20%);
  pointer-events: none;
}

.auth-frame {
  position: relative;
  z-index: 1;
  width: min(460px, 100%);
}

.auth-card {
  background: var(--aw-shell);
  backdrop-filter: blur(18px);
  border: 1px solid var(--aw-border);
  box-shadow: var(--aw-shadow);
  border-radius: 30px;
  padding: 34px;
}

.back-link {
  font-size: 13px;
  color: var(--aw-text-muted);
}

.auth-card h2 {
  margin: 18px 0 8px;
  font-size: 2.4rem;
  color: var(--aw-text);
}

.auth-subtitle {
  margin: 0 0 28px;
  color: var(--aw-text-soft);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--aw-text-soft);
}

.form-group input {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--aw-border);
  border-radius: 16px;
  background: var(--aw-paper-strong);
  color: var(--aw-text);
  font: inherit;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.form-group input:focus {
  outline: none;
  border-color: var(--aw-accent);
  box-shadow: 0 0 0 4px rgba(201, 111, 69, 0.12);
  transform: translateY(-1px);
}

.message-strip {
  padding: 12px 14px;
  border-radius: 16px;
  margin-bottom: 16px;
  font-size: 14px;
}

.error-strip {
  color: #a84d3a;
  background: rgba(185, 95, 74, 0.12);
  border: 1px solid rgba(185, 95, 74, 0.2);
}

.success-strip {
  color: #3e6b54;
  background: rgba(83, 125, 98, 0.12);
  border: 1px solid rgba(83, 125, 98, 0.18);
}

.submit-btn {
  width: 100%;
  padding: 15px 18px;
  border: none;
  border-radius: 18px;
  background: var(--aw-accent);
  color: #fff8f2;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.2s ease, background-color 0.2s ease, opacity 0.2s ease;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: var(--aw-accent-strong);
}

.submit-btn:disabled {
  opacity: 0.72;
  cursor: not-allowed;
}

.footer-links {
  margin-top: 22px;
  display: flex;
  gap: 8px;
  font-size: 14px;
  color: var(--aw-text-muted);
}

@media (max-width: 960px) {
  .auth-shell {
    padding: 20px;
  }
}

@media (max-width: 640px) {
  .auth-card {
    padding: 26px 20px;
  }

  .auth-card h2 {
    font-size: 2rem;
  }
}
</style>
