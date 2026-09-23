<script setup lang="ts">
import axios from "axios";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { archiveAgentInstance, listAgentInstances, openAgentInstance } from "../api/agents";
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
const editingCard = ref<Card | null>(null);
const archiveCard = ref<Card | null>(null);
const archiveLoading = ref(false);
const loading = ref(false);

const visibleCards = computed(() => filterCards(cards.value, query.value));

function findCard(id: string): Card | null {
  return cards.value.find((card) => card.agent_instance_id === id) || null;
}

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

function openCreate() {
  editingCard.value = null;
  modalOpen.value = true;
}

function closeModal() {
  modalOpen.value = false;
  editingCard.value = null;
}

function startEdit(id: string) {
  editingCard.value = findCard(id);
  if (!editingCard.value) {
    return;
  }
  modalOpen.value = true;
}

function startArchive(id: string) {
  archiveCard.value = findCard(id);
}

function cancelArchive() {
  if (archiveLoading.value) {
    return;
  }
  archiveCard.value = null;
}

async function confirmArchive() {
  if (!archiveCard.value) {
    return;
  }
  archiveLoading.value = true;
  error.value = "";
  const instanceId = archiveCard.value.agent_instance_id;
  try {
    await archiveAgentInstance(instanceId);
    archiveCard.value = null;
    await loadCards();
  } catch (err) {
    error.value = apiErrorMessage(err, "归档失败");
    archiveCard.value = null;
    if (axios.isAxiosError(err) && err.response?.status === 404) {
      await loadCards();
    }
  } finally {
    archiveLoading.value = false;
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
          <button class="agent-btn agent-create-btn" type="button" @click="openCreate">+ 新建智能体</button>
          <button class="agent-btn agent-btn-ghost" type="button" @click="logout">退出登录</button>
        </div>
      </header>
      <p v-if="error" class="agent-error">{{ error }}</p>
      <p v-if="!loading && !visibleCards.length" class="agent-empty">还没有智能体，点击「新建智能体」开始。</p>
      <div class="agent-grid">
        <AgentCard
          v-for="card in visibleCards"
          :key="card.agent_instance_id"
          :card="card"
          @click="openCard"
          @edit="startEdit"
          @archive="startArchive"
        />
      </div>
    </div>
    <CreateAgentModal :open="modalOpen" :card="editingCard" @close="closeModal" @created="loadCards" @saved="loadCards" />
    <div v-if="archiveCard" class="agent-modal-mask agent-archive-mask" @click.self="cancelArchive">
      <div class="agent-modal agent-modal-sm" role="dialog" aria-modal="true">
        <div class="agent-modal-head">
          <h2>归档智能体</h2>
          <button class="agent-icon-btn" type="button" aria-label="关闭" @click="cancelArchive">×</button>
        </div>
        <p>
          归档「{{ archiveCard.title }}」后，广场不再展示该卡片，对话入口失效，同名以后可再建。这不是物理删除。
        </p>
        <div class="agent-modal-actions">
          <button class="agent-btn agent-btn-ghost agent-archive-cancel" type="button" @click="cancelArchive">取消</button>
          <button
            class="agent-btn agent-btn-danger agent-archive-confirm"
            type="button"
            :disabled="archiveLoading"
            @click="confirmArchive"
          >
            {{ archiveLoading ? "归档中..." : "确认归档" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
