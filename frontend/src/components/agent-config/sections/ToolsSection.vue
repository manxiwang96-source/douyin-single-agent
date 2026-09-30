<template>
  <section class="agent-editor-card">
    <div class="agent-section-heading">
      <div>
        <h2>工具与工作流</h2>
        <p>工具列表来自服务端目录，勾选后写入草稿。当前时间不可关闭。线索发现使用 discover_leads。</p>
      </div>
    </div>
    <p v-if="loadError" class="agent-error">{{ loadError }}</p>
    <label
      class="agent-tool-row"
      :class="{ 'is-locked': isLocked(tool) }"
      v-for="tool in catalog"
      :key="tool.tool_code"
    >
      <input
        type="checkbox"
        :value="tool.tool_code"
        :checked="isEnabled(tool.tool_code)"
        :disabled="isLocked(tool)"
        @change="onToolChange(tool, $event)"
      />
      <span>
        <strong>{{ tool.display_name }}</strong>
        <small>{{ tool.tool_code }} · {{ tool.description || (isLocked(tool) ? "平台必需工具" : "仅在白名单内对模型可见和可执行") }}</small>
      </span>
    </label>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  BUILTIN_TOOL_CODE,
  DISCOVER_LEADS_TOOL_CODE,
  listAgentTools,
  pendingWorkflowCodes,
  resolveToolCode,
  updateAgentTools,
  withRequiredDatetime,
  type ToolCatalogItem,
} from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";
import type { AgentConfigDraft } from "../../../lib/agentConfig";

const props = defineProps<{
  draft: AgentConfigDraft;
}>();

const route = useRoute();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const tools = ref<ToolCatalogItem[]>([]);
const loadError = ref("");
const saving = ref(false);

const catalog = computed(() => {
  const seen = new Set<string>();
  const items: ToolCatalogItem[] = [];
  for (const item of tools.value) {
    const tool_code = resolveToolCode(item.tool_code);
    if (!tool_code || seen.has(tool_code)) continue;
    seen.add(tool_code);
    items.push({ ...item, tool_code });
  }
  return items;
});

function isLocked(tool: ToolCatalogItem) {
  return Boolean(tool.built_in) || resolveToolCode(tool.tool_code) === BUILTIN_TOOL_CODE;
}

function isEnabled(code: string) {
  return withRequiredDatetime(props.draft.enabled_tool_codes).includes(resolveToolCode(code));
}

function syncEnabledCodes(codes: Iterable<string>) {
  props.draft.enabled_tool_codes = withRequiredDatetime(codes);
}

function applyPendingWorkflows() {
  if (pendingWorkflowCodes.codes !== null) {
    props.draft.workflow_codes = [...pendingWorkflowCodes.codes];
  }
}

async function loadCatalog() {
  const id = agentInstanceId.value;
  if (!id) return;
  loadError.value = "";
  try {
    const result = await listAgentTools(id);
    tools.value = Array.isArray(result?.items) ? result.items : [];
    syncEnabledCodes(props.draft.enabled_tool_codes);
  } catch (err) {
    loadError.value = apiErrorMessage(err, "加载工具目录失败");
  }
}

function onToolChange(tool: ToolCatalogItem, event: Event) {
  const target = event.target;
  const checked = target instanceof HTMLInputElement && target.checked;
  void toggleTool(tool, checked);
}

async function toggleTool(tool: ToolCatalogItem, checked: boolean) {
  const code = resolveToolCode(tool.tool_code);
  if (!code || isLocked(tool) || code === BUILTIN_TOOL_CODE) return;
  const next = new Set(withRequiredDatetime(props.draft.enabled_tool_codes));
  if (checked) next.add(code);
  else next.delete(code);
  if (code === DISCOVER_LEADS_TOOL_CODE && checked) next.add(DISCOVER_LEADS_TOOL_CODE);
  syncEnabledCodes(next);
  const id = agentInstanceId.value;
  if (!id) return;
  saving.value = true;
  try {
    await updateAgentTools(id, props.draft.enabled_tool_codes);
  } catch (err) {
    loadError.value = apiErrorMessage(err, "保存工具勾选失败");
  } finally {
    saving.value = false;
  }
}

if (pendingWorkflowCodes.codes === null) {
  pendingWorkflowCodes.codes = [...props.draft.workflow_codes];
} else {
  applyPendingWorkflows();
}

watch(() => pendingWorkflowCodes.codes, applyPendingWorkflows);

onMounted(loadCatalog);
</script>
