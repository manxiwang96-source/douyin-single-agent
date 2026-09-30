<template>
  <aside class="agent-editor-preview">
    <div class="agent-preview-heading">
      <div>
        <span>调试环境</span>
        <h2>{{ agentTitle }}</h2>
      </div>
      <span class="agent-preview-dot">● 草稿</span>
    </div>
    <p class="agent-preview-note">调试环境，使用未发布草稿。每条消息都会按当前 draft 真实执行。</p>
    <p v-if="debugError" class="agent-error">{{ debugError }}</p>
    <div class="agent-preview-messages">
      <div class="agent-preview-welcome">{{ draft.welcome_message || "你好，我是你的智能体。请在左侧配置欢迎语。" }}</div>
      <div
        v-for="(item, index) in visibleMessages"
        :key="item.messageId || item.clientMessageId || `${item.role}-${index}`"
        :class="item.role === 'user' ? 'agent-preview-welcome' : 'agent-preview-answer'"
      >
        {{ item.content }}
      </div>
      <HitlCard
        :visible="hitl.visible"
        :kind="hitl.kind"
        :tool="hitl.tool"
        :prompt="hitl.prompt"
        :params="hitl.params"
        :reason="hitl.reason"
        :resource-code="hitl.resourceCode"
        :detail="hitl.detail"
        :disabled="sending"
        @approve="onApprove"
        @skip="onSkip"
        @reject="onReject"
      />
    </div>
    <div class="agent-preview-examples">
      <button v-for="question in draft.example_questions" :key="question" type="button" @click="fillInput(question)">{{ question }}</button>
    </div>
    <textarea :value="localInput" rows="3" placeholder="输入消息调试未发布草稿" :disabled="sending || hitl.visible" @input="onInput" />
    <button class="agent-btn" type="button" :disabled="!localInput.trim() || sending || !threadId || hitl.visible" @click="sendDebug">发送</button>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { decideApproval } from "../../api/agentConfig";
import { getThread, openDebugThread, postMessage, resumeThread } from "../../api/threads";
import HitlCard from "../../components/HitlCard.vue";

type HitlKind = "media" | "import" | "skill" | "script" | "tool";
import {
  appendPendingToken,
  buildChatView,
  markRequestMessage,
  mergeChatMessages,
  optimisticMessages,
  type ChatMessage,
} from "../../lib/chat";
import { apiErrorMessage } from "../../lib/errors";
import type { AgentConfigDraft } from "../../lib/agentConfig";

const props = defineProps<{
  agentTitle: string;
  draft: AgentConfigDraft;
  previewInput: string;
  previewAnswer: string;
}>();

const emit = defineEmits<{
  "update:previewInput": [value: string];
  preview: [];
}>();

type DebugHitl = {
  visible: boolean;
  kind?: HitlKind;
  tool: unknown;
  prompt: string;
  params: Record<string, unknown>;
  reason: string;
  resourceCode: string;
  detail: string;
  approvalId: string;
};

const emptyHitl = (): DebugHitl => ({
  visible: false,
  kind: undefined,
  tool: null,
  prompt: "",
  params: {},
  reason: "",
  resourceCode: "",
  detail: "",
  approvalId: "",
});

const route = useRoute();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const threadId = ref("");
const sending = ref(false);
const debugError = ref("");
const messages = ref<ChatMessage[]>([]);
const localInput = ref(props.previewInput || "");
const hitl = ref<DebugHitl>(emptyHitl());

watch(
  () => props.previewInput,
  (value) => {
    if (value !== localInput.value) localInput.value = value;
  },
);

const visibleMessages = computed(() =>
  messages.value.filter((item) => item.role === "user" || item.role === "assistant"),
);

function fillInput(value: string) {
  localInput.value = value;
  emit("update:previewInput", value);
}

function onInput(event: Event) {
  const value = (event.target as HTMLTextAreaElement).value;
  localInput.value = value;
  emit("update:previewInput", value);
}

function hitlKindFromInterrupt(pending: Record<string, unknown> | null | undefined): HitlKind | undefined {
  if (!pending) return undefined;
  const kind = String(pending.approval_kind || "");
  const type = String(pending.type || "");
  if (kind === "import" || type === "import" || type === "review_import") return "import";
  if (kind === "skill" || type === "review_skill") return "skill";
  if (kind === "script" || type === "review_skill_script") return "script";
  if (kind === "tool" || type === "review_tool") return "tool";
  if (type === "review_media") return "media";
  return undefined;
}

function hitlDetail(pending: Record<string, unknown>): string {
  const parts: string[] = [];
  if (pending.skill_name) parts.push(`Skill：${pending.skill_name}`);
  if (pending.script_path) parts.push(`脚本：${pending.script_path}`);
  if (pending.subject) parts.push(`主题：${pending.subject}`);
  return parts.join(" · ");
}

function applyInterrupt(thread: Record<string, unknown>) {
  const view = buildChatView(thread);
  const pending = view.interrupt;
  const kind = hitlKindFromInterrupt(pending);
  if (!pending || !kind) {
    hitl.value = emptyHitl();
    return;
  }
  hitl.value = {
    visible: true,
    kind,
    tool: pending.tool ?? (kind === "tool" ? pending.resource_code : null),
    prompt: String(pending.prompt || ""),
    params: (pending.params as Record<string, unknown>) || {},
    reason: String(pending.reason || ""),
    resourceCode: String(pending.resource_code || ""),
    detail: hitlDetail(pending),
    approvalId: String(pending.approval_id || ""),
  };
}

function applyThread(thread: Record<string, unknown>, settledClientMessageId?: string) {
  const view = buildChatView(thread);
  messages.value = mergeChatMessages(view.messages, messages.value, settledClientMessageId);
  applyInterrupt(thread);
}

async function bootstrapDebugThread() {
  if (!agentInstanceId.value) return;
  debugError.value = "";
  try {
    const opened = await openDebugThread(agentInstanceId.value);
    threadId.value = String(opened.thread_id || "");
    if (!threadId.value) return;
    const thread = await getThread(threadId.value);
    applyThread(thread);
  } catch (err) {
    debugError.value = apiErrorMessage(err, "打开调试线程失败");
  }
}

async function sendDebug() {
  const content = localInput.value.trim();
  if (!content || !threadId.value || sending.value || hitl.value.visible) return;
  sending.value = true;
  debugError.value = "";
  const clientMessageId = crypto.randomUUID();
  localInput.value = "";
  emit("update:previewInput", "");
  messages.value = [...messages.value, ...optimisticMessages(content, clientMessageId)];
  try {
    const thread = await postMessage(threadId.value, content, clientMessageId, {
      onToken: (delta) => {
        messages.value = appendPendingToken(messages.value, clientMessageId, delta);
      },
    });
    applyThread(thread, clientMessageId);
  } catch (err) {
    messages.value = markRequestMessage(messages.value, clientMessageId, "error");
    debugError.value = apiErrorMessage(err, "调试发送失败");
  } finally {
    sending.value = false;
  }
}

async function decideAndResume(approved: boolean, resumeBody: Record<string, unknown>) {
  if (!threadId.value || sending.value) return;
  sending.value = true;
  debugError.value = "";
  try {
    if (hitl.value.approvalId) {
      await decideApproval(hitl.value.approvalId, approved, approved ? "用户在调试区批准" : "用户在调试区拒绝");
    }
    const thread = await resumeThread(threadId.value, resumeBody);
    applyThread(thread);
  } catch (err) {
    debugError.value = apiErrorMessage(err, approved ? "审批失败" : "拒绝失败");
  } finally {
    sending.value = false;
  }
}

async function onApprove(payload: { prompt: string; params: Record<string, unknown> }) {
  if (hitl.value.kind === "media") {
    await decideAndResume(true, { action: "approve", prompt: payload.prompt, params: payload.params });
    return;
  }
  await decideAndResume(true, { action: "approve_once" });
}

async function onSkip() {
  await decideAndResume(false, { action: "skip" });
}

async function onReject() {
  await decideAndResume(false, { action: "deny" });
}

void props.previewAnswer;
onMounted(bootstrapDebugThread);
</script>
