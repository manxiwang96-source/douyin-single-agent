<template>
  <section class="agent-editor-card agent-versions-section">
    <div class="agent-section-heading">
      <div>
        <h2>版本</h2>
        <p>列出当前智能体的配置版本，并标明 published / draft。发布请用顶栏「发布配置」。</p>
      </div>
      <button class="agent-btn agent-btn-ghost" type="button" :disabled="loading" @click="loadVersions">刷新</button>
    </div>
    <p v-if="loadError" class="agent-error">{{ loadError }}</p>
    <p v-else-if="loading" class="agent-helper">正在加载版本...</p>
    <p v-else-if="!versions.length" class="agent-side-empty">暂无配置版本。</p>
    <ul v-else class="agent-version-list">
      <li
        v-for="item in versions"
        :key="item.config_version_id"
        class="agent-version-row"
        :class="rowClass(item.status)"
        :data-version-status="item.status"
        :data-version-id="item.config_version_id"
      >
        <div>
          <strong>v{{ item.version_no }}</strong>
          <span class="agent-pill" :class="rowClass(item.status)">{{ statusLabel(item.status) }}</span>
        </div>
        <p>{{ item.config_version_id }}</p>
        <p v-if="item.updated_at">更新于 {{ formatTime(item.updated_at) }}</p>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { http } from "../../../api/http";
import type { AgentConfig } from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";

const route = useRoute();
const versions = ref<AgentConfig[]>([]);
const loading = ref(false);
const loadError = ref("");

function statusLabel(status: string): string {
  if (status === "published") return "published";
  if (status === "draft") return "draft";
  return status || "unknown";
}

function rowClass(status: string): string {
  if (status === "published") return "is-published";
  if (status === "draft") return "is-draft";
  return "";
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

async function loadVersions() {
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  loading.value = true;
  loadError.value = "";
  try {
    const response = await http.get("/v1/agent-instances/" + id + "/config/versions");
    const items = Array.isArray(response?.data?.items) ? response.data.items : [];
    versions.value = items as AgentConfig[];
  } catch (err) {
    loadError.value = apiErrorMessage(err, "加载版本列表失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadVersions);
</script>