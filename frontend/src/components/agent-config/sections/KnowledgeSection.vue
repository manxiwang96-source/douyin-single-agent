<template>
  <section class="agent-editor-card agent-knowledge-section">
    <div class="agent-section-heading">
      <div>
        <h2>知识库</h2>
        <p>仅能选择当前用户当前智能体的文档；勾选写入 draft 知识关系。支持上传 .md / .txt。</p>
      </div>
      <label class="agent-btn agent-btn-soft agent-knowledge-upload">
        {{ uploading ? "上传中..." : "上传 md/txt" }}
        <input
          class="agent-knowledge-file"
          type="file"
          accept=".md,.txt,text/markdown,text/plain"
          :disabled="uploading"
          @change="onFileChange"
        />
      </label>
    </div>
    <p class="agent-knowledge-hint">只接受 .md 或 .txt，最大 1MB。上传失败或接口 404 时不影响欢迎语、示例等其它表单。</p>
    <p v-if="localError" class="agent-error agent-knowledge-error">{{ localError }}</p>
    <p v-if="localNotice" class="agent-knowledge-notice">{{ localNotice }}</p>
    <label
      v-for="document in documentsToShow"
      :key="document.document_id"
      class="agent-tool-row agent-knowledge-row"
      :class="{ 'is-disabled': document.status !== 'ready' }"
    >
      <input
        v-model="draft.knowledge_document_ids"
        type="checkbox"
        :value="document.document_id"
        :disabled="document.status !== 'ready'"
        @change="persistSelection"
      />
      <span>
        <strong>{{ document.title }}</strong>
        <small>{{ document.filename }} · {{ statusLabel(document.status) }}</small>
      </span>
    </label>
    <p v-if="!documentsToShow.length" class="agent-side-empty">当前实例暂无知识库文档。</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  isAllowedKnowledgeFilename,
  isKnowledgeApiMissing,
  listAgentKnowledge,
  MAX_KNOWLEDGE_UPLOAD_BYTES,
  uploadAgentKnowledge,
  updateAgentConfig,
  type KnowledgeDocument,
} from "../../../api/agentConfig";
import { apiErrorMessage } from "../../../lib/errors";
import type { AgentConfigDraft } from "../../../lib/agentConfig";

const props = defineProps<{
  draft: AgentConfigDraft;
  documents: KnowledgeDocument[];
}>();

const route = useRoute();
const localDocuments = ref<KnowledgeDocument[]>([...props.documents]);
const uploading = ref(false);
const localError = ref("");
const localNotice = ref("");

const documentsToShow = computed(() => localDocuments.value);

watch(
  () => props.documents,
  (docs) => {
    const incoming = Array.isArray(docs) ? docs : [];
    if (!incoming.length) return;
    const byId = new Map(localDocuments.value.map((item) => [item.document_id, item]));
    for (const item of incoming) byId.set(item.document_id, item);
    localDocuments.value = Array.from(byId.values());
  },
  { deep: true },
);

function statusLabel(status: string): string {
  if (status === "ready") return "可用";
  if (status === "uploaded" || status === "indexing") return status;
  return status || "未知";
}

function rememberDocument(item: KnowledgeDocument) {
  const next = localDocuments.value.filter((doc) => doc.document_id !== item.document_id);
  next.push(item);
  localDocuments.value = next;
  if (!props.draft.knowledge_document_ids.includes(item.document_id)) {
    props.draft.knowledge_document_ids.push(item.document_id);
  }
}

async function loadDocuments() {
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  try {
    const result = await listAgentKnowledge(id);
    const items = Array.isArray(result?.items) ? result.items : [];
    if (items.length) localDocuments.value = items;
    if (Array.isArray(result?.selected_document_ids) && !props.draft.knowledge_document_ids.length) {
      props.draft.knowledge_document_ids = [...result.selected_document_ids];
    }
  } catch (err) {
    if (isKnowledgeApiMissing(err)) {
      localNotice.value = "知识接口暂不可用，其它配置仍可继续编辑。";
      return;
    }
    localError.value = apiErrorMessage(err, "加载知识文档失败");
  }
}

async function persistSelection() {
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  try {
    await updateAgentConfig(id, { knowledge_document_ids: [...props.draft.knowledge_document_ids] });
  } catch (err) {
    if (isKnowledgeApiMissing(err)) {
      localNotice.value = "知识勾选暂无法同步到服务端，已保留在当前草稿表单中。";
      return;
    }
    localError.value = apiErrorMessage(err, "保存知识勾选失败");
  }
}

async function onFileChange(event: Event) {
  const input = event.target;
  if (!(input instanceof HTMLInputElement)) return;
  const file = input.files && input.files[0];
  input.value = "";
  localError.value = "";
  if (!file) return;
  if (!isAllowedKnowledgeFilename(file.name)) {
    localError.value = "只支持上传 .md 或 .txt 文件。";
    return;
  }
  if (file.size > MAX_KNOWLEDGE_UPLOAD_BYTES) {
    localError.value = "文件超过 1MB 上限。";
    return;
  }
  const id = String(route.params.agentInstanceId || "");
  if (!id) return;
  uploading.value = true;
  try {
    const item = await uploadAgentKnowledge(id, file);
    rememberDocument(item);
    localNotice.value = `已上传 ${item.filename}，并默认勾进当前草稿。`;
  } catch (err) {
    if (isKnowledgeApiMissing(err)) {
      localNotice.value = "知识上传接口暂不可用（404），不影响欢迎语、示例等其它表单。";
      return;
    }
    localError.value = apiErrorMessage(err, "上传知识文件失败");
  } finally {
    uploading.value = false;
  }
}

onMounted(loadDocuments);
</script>
