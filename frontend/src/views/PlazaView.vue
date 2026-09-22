<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { listAgentInstances, openAgentInstance } from "../api/agents";
import AgentCard from "../components/AgentCard.vue";
import CreateAgentModal from "../components/CreateAgentModal.vue";
import { apiErrorMessage } from "../lib/errors";
import { filterCards, mapPlazaCards, type AgentCard as Card } from "../lib/plaza";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();
const cards = ref<Card[]>([]);
const query = ref("");
const error = ref("");
const modalOpen = ref(false);
const loading = ref(false);

const visibleCards = computed(() => filterCards(cards.value, query.value));

async function loadCards() {
  loading.value = true;
  error.value = "";
  try {
    const payload = await listAgentInstances();
    cards.value = mapPlazaCards(payload.items || []);
  } catch (err) {
    error.value = apiErrorMessage(err, "加载广场失败");
  } finally {
    loading.value = false;
  }
}

async function openCard(id: string) {
  error.value = "";
  try {
    const opened = await openAgentInstance(id);
    await router.push({
      name: "chat",
      params: { agentInstanceId: opened.agent_instance_id },
      query: { thread_id: opened.thread_id },
    });
  } catch (err) {
    error.value = apiErrorMessage(err, "打开对话失败");
  }
}

async function logout() {
  await auth.logout();
  await router.replace({ name: "login" });
}

onMounted(loadCards);
</script>

<template>
  <div class="agent-page">
    <div class="agent-wrap">
      <header class="agent-topbar">
        <div>
          <h1 class="agent-title">我的智能体</h1>
          <p class="agent-subtitle">一人可创建多个抖音运营助手实例</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input v-model="query" class="agent-search" placeholder="搜索名称或简介" />
          <button class="agent-btn" type="button" @click="modalOpen = true">+ 新建智能体</button>
          <button class="agent-btn agent-btn-ghost" type="button" @click="logout">退出登录</button>
        </div>
      </header>
      <p v-if="error" class="agent-error">{{ error }}</p>
      <p v-if="!loading && !visibleCards.length" class="agent-empty">还没有智能体，点击「新建智能体」开始。</p>
      <div class="agent-grid">
        <AgentCard v-for="card in visibleCards" :key="card.agent_instance_id" :card="card" @click="openCard" />
      </div>
    </div>
    <CreateAgentModal :open="modalOpen" @close="modalOpen = false" @created="loadCards" />
  </div>
</template>
