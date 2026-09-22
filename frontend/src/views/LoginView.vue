<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiErrorMessage } from "../lib/errors";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const mode = ref<"login" | "register">("login");
const loginName = ref("");
const password = ref("");
const error = ref("");
const loading = ref(false);

async function submit() {
  error.value = "";
  const name = loginName.value.trim();
  if (!name) {
    error.value = "请输入账号";
    return;
  }
  if (mode.value === "register" && password.value.length < 8) {
    error.value = "密码至少 8 位";
    return;
  }
  loading.value = true;
  try {
    if (mode.value === "register") {
      await auth.register(name, password.value);
    } else {
      await auth.login(name, password.value);
    }
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/agents";
    await router.replace(redirect || "/agents");
  } catch (err) {
    error.value = apiErrorMessage(err, mode.value === "register" ? "注册失败" : "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="agent-page agent-login">
    <div class="agent-login-card">
      <h1 class="agent-title">抖音运营助手</h1>
      <p class="agent-subtitle">登录后进入智能体广场，再点卡片开始对话。</p>
      <div class="agent-tabs">
        <button class="agent-tab" :class="{ 'is-active': mode === 'login' }" type="button" @click="mode = 'login'">登录</button>
        <button class="agent-tab" :class="{ 'is-active': mode === 'register' }" type="button" @click="mode = 'register'">注册</button>
      </div>
      <form @submit.prevent="submit">
        <label class="agent-field">
          账号
          <input v-model="loginName" autocomplete="username" />
        </label>
        <label class="agent-field">
          密码
          <input v-model="password" type="password" autocomplete="current-password" />
        </label>
        <button class="agent-btn" type="submit" :disabled="loading">
          {{ loading ? "提交中..." : mode === "register" ? "注册并登录" : "登录" }}
        </button>
        <p v-if="error" class="agent-error">{{ error }}</p>
      </form>
    </div>
  </div>
</template>
