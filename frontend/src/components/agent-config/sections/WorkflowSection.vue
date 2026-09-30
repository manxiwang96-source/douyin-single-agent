<template>
  <section class="agent-editor-card">
    <div class="agent-section-heading">
      <div>
        <h2>工作流</h2>
        <p>工作流来自当前模板目录。自定义智能体默认不绑定 Dify，除非目录允许且用户勾选。</p>
      </div>
    </div>
    <p v-if="loadError" class="agent-error">{{ loadError }}</p>
    <p v-if="!workflows.length" class="agent-workflow-empty">当前模板没有可勾选的工作流。自定义智能体默认不绑定 Dify。</p>
    <label class="agent-tool-row" v-for="item in workflows" :key="item.code">
      <input
        type="checkbox"
        :value="item.code"
        :checked="isEnabled(item.code)"
        @change="onWorkflowChange(item.code, $event)"
      />
      <span>
        <strong>{{ item.display_name }}</strong>
        <small>{{ item.code }}</small>
      </span>
    </label>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { getAgentSidebar } from "../../../api/agents";
import { pendingWorkflowCodes, type WorkflowCatalogItem } from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";

const route = useRoute();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const workflows = ref<WorkflowCatalogItem[]>([]);
const loadError = ref("");

function isEnabled(code: string) {
  return (pendingWorkflowCodes.codes || []).includes(code);
}

function allowedCodes() {
  return new Set(workflows.value.map((item) => item.code));
}

function setPending(codes: string[]) {
  const allowed = allowedCodes();
  pendingWorkflowCodes.codes = codes.filter((code) => allowed.has(code));
}

function onWorkflowChange(code: string, event: Event) {
  const target = event.target;
  toggleWorkflow(code, target instanceof HTMLInputElement && target.checked);
}

function toggleWorkflow(code: string, checked: boolean) {
  const current = new Set(pendingWorkflowCodes.codes || []);
  if (checked) current.add(code);
  else current.delete(code);
  setPending([...current]);
}

async function loadWorkflows() {
  const id = agentInstanceId.value;
  if (!id) return;
  loadError.value = "";
  try {
    const sidebar = await getAgentSidebar(id);
    const items = Array.isArray(sidebar?.workflows) ? sidebar.workflows : [];
    workflows.value = items
      .map((item) => {
        const record = item as Record<string, unknown>;
        return {
          code: String(record.code || "").trim(),
          display_name: String(record.display_name || record.code || ""),
          enabled: Boolean(record.enabled),
        };
      })
      .filter((item) => item.code);
    const allowed = allowedCodes();
    const current = pendingWorkflowCodes.codes || [];
    pendingWorkflowCodes.codes = current.filter((code) => allowed.has(code));
  } catch (err) {
    loadError.value = apiErrorMessage(err, "加载工作流目录失败");
  }
}

onMounted(loadWorkflows);
</script>
