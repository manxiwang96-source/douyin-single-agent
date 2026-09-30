<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { decideApproval } from "../api/agentConfig";
import { http } from "../api/http";
import { getAgentSidebar, openAgentInstance } from "../api/agents";
import { fetchAuthBlob, getThread, postMessage, resumeThread } from "../api/threads";
import ChatSidebar from "../components/ChatSidebar.vue";
import HitlCard from "../components/HitlCard.vue";
import TaskProgressPanel from "../components/TaskProgressPanel.vue";
import {
  appendPendingToken,
  approveResumePayload,
  buildChatView,
  clearPendingDraft,
  currentActivityLabel,
  EMPTY_CHAT_HINT,
  freezeSkipProgress,
  isSkippedProgress,
  localThinkingProgress,
  markRequestMessage,
  mergeChatMessages,
  messageTime,
  optimisticMessages,
  PENDING_REPLY_TEXT,
  publishedChatWelcome,
  shouldApplyTaskProgress,
  shouldShowOfficialWelcome,
  sidebarView,
  skipResumePayload,
  threadProgress,
  type ChatMessage,
  type SidebarView,
  type TaskProgress,
} from "../lib/chat";
import { apiErrorMessage } from "../lib/errors";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const threadId = ref(typeof route.query.thread_id === "string" ? route.query.thread_id : "");
const title = ref("运营助手");
const avatarSrc = ref("");
const error = ref("");
const activeRequests = ref(0);
const sending = computed(() => activeRequests.value > 0);
const draft = ref("");
const messages = ref<ChatMessage[]>([]);
const inputEnabled = ref(true);
const threadKind = ref("official");
const welcomeMessage = ref("");
const exampleQuestions = ref<string[]>([]);
type HitlKind = "media" | "import" | "skill" | "script" | "tool";

type ChatHitl = {
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

const emptyHitl = (): ChatHitl => ({
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

const hitl = ref<ChatHitl>(emptyHitl());
const showOfficialWelcome = computed(() =>
  shouldShowOfficialWelcome({
    threadKind: threadKind.value,
    messageCount: messages.value.length,
    hitlVisible: hitl.value.visible,
  }),
);
const sidebar = ref<SidebarView>(sidebarView({}));
const bootstrapVersion = ref(0);
const latestRequestVersion = ref(0);
const activeRoundId = ref<string | null>(null);
const skipFrozen = ref(false);
const taskProgress = ref<TaskProgress>(threadProgress(null));
const blobUrls = new Map<string, string>();
let avatarObjectUrl = "";

function revokeAvatar() {
  if (avatarObjectUrl) {
    URL.revokeObjectURL(avatarObjectUrl);
    avatarObjectUrl = "";
  }
}

function applyTaskProgress(incoming: TaskProgress) {
  if (!shouldApplyTaskProgress(incoming, { activeRoundId: activeRoundId.value, skipFrozen: skipFrozen.value })) {
    return;
  }
  taskProgress.value = incoming;
}

function applyProgressFromThread(thread: Record<string, unknown>) {
  applyTaskProgress(threadProgress(thread));
}

function applyStreamProgress(progress: TaskProgress, clientMessageId?: string) {
  applyTaskProgress(progress);
  if (progress.phase === "running") {
    messages.value = clearPendingDraft(messages.value, clientMessageId);
  }
}

function bubbleText(item: ChatMessage): string {
  if (item.pending && (!item.content || item.content === PENDING_REPLY_TEXT)) {
    return currentActivityLabel(taskProgress.value);
  }
  return item.content;
}

function applyStreamToken(delta: string, clientMessageId: string) {
  messages.value = appendPendingToken(messages.value, clientMessageId, delta);
}

function isTimeoutError(err: unknown): boolean {
  const value = err as { code?: string; message?: string } | null;
  return value?.code === "ECONNABORTED" || value?.code === "ETIMEDOUT" || /timeout/i.test(value?.message || "");
}

async function resolvePreview(url: string): Promise<string> {
  if (blobUrls.has(url)) return blobUrls.get(url) || url;
  try {
    const blob = await fetchAuthBlob(url);
    const objectUrl = URL.createObjectURL(blob);
    blobUrls.set(url, objectUrl);
    return objectUrl;
  } catch {
    return url;
  }
}

function hitlKindFromInterrupt(pending: Record<string, unknown> | null | undefined): HitlKind | undefined {
  if (!pending) return undefined;
  const kind = String(pending.approval_kind || "");
  const type = String(pending.type || "");
  if (kind === "import" || type === "import" || type === "review_import") return "import";
  if (kind === "skill" || type === "review_skill") return "skill";
  if (kind === "script" || type === "review_skill_script") return "script";
  if (kind === "tool" || type === "review_tool") return "tool";
  return "media";
}

function hitlDetail(pending: Record<string, unknown>): string {
  const parts: string[] = [];
  if (pending.skill_name) parts.push(`Skill：${pending.skill_name}`);
  if (pending.script_path) parts.push(`脚本：${pending.script_path}`);
  if (pending.subject) parts.push(`主题：${pending.subject}`);
  return parts.join(" · ");
}

function applyInterrupt(view: { interrupt?: Record<string, unknown> | null }) {
  const pending = view.interrupt;
  if (!pending) {
    hitl.value = emptyHitl();
    return;
  }
  const kind = hitlKindFromInterrupt(pending) || "media";
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

function isMediaHitl(): boolean {
  return !hitl.value.kind || hitl.value.kind === "media";
}

async function applyThread(thread: Record<string, unknown>, settledClientMessageId?: string, version = bootstrapVersion.value, requestVersion?: number) {
  if (thread.thread_kind) threadKind.value = String(thread.thread_kind);
  const view = buildChatView(thread, "");
  inputEnabled.value = view.chat_input_enabled;
  applyInterrupt(view);
  const merged = mergeChatMessages(view.messages, messages.value, settledClientMessageId);
  const nextMessages: ChatMessage[] = [];
  for (const item of merged) {
    const previews = [];
    for (const preview of item.previews) {
      previews.push({ widget: preview.widget, url: await resolvePreview(preview.url) });
    }
    nextMessages.push({ ...item, previews });
  }
  if (version === bootstrapVersion.value && (requestVersion === undefined || requestVersion === latestRequestVersion.value)) {
    messages.value = nextMessages;
  }
}

async function loadSidebar() {
  const payload = await getAgentSidebar(agentInstanceId.value);
  sidebar.value = sidebarView(payload);
  title.value = String(payload.title || title.value);
  const avatarUrl = `/v1/agent-instances/${agentInstanceId.value}/avatar`;
  try {
    revokeAvatar();
    const blob = await fetchAuthBlob(avatarUrl);
    avatarObjectUrl = URL.createObjectURL(blob);
    avatarSrc.value = avatarObjectUrl;
  } catch {
    avatarSrc.value = "";
  }
  return payload;
}

async function loadPublishedWelcome(sidebarPayload?: Record<string, unknown>) {
  try {
    const response = await http.get(`/v1/agent-instances/${agentInstanceId.value}/config/versions`);
    const fromPublished = publishedChatWelcome(response.data);
    if (fromPublished.welcomeMessage || fromPublished.exampleQuestions.length) return fromPublished;
  } catch {
    // Keep the old empty state when published config is unavailable.
  }
  return publishedChatWelcome(sidebarPayload);
}

async function bootstrap() {
  const version = ++bootstrapVersion.value;
  error.value = "";
  welcomeMessage.value = "";
  exampleQuestions.value = [];
  threadKind.value = "official";
  try {
    const opened = await openAgentInstance(agentInstanceId.value);
    if (version !== bootstrapVersion.value) return;
    threadId.value = opened.thread_id;
    const [thread, sidebarPayload] = await Promise.all([getThread(opened.thread_id), loadSidebar()]);
    const welcome = await loadPublishedWelcome(sidebarPayload);
    if (version !== bootstrapVersion.value) return;
    welcomeMessage.value = welcome.welcomeMessage;
    exampleQuestions.value = welcome.exampleQuestions;
    await applyThread(thread, undefined, version);
    const progress = threadProgress(thread);
    activeRoundId.value = progress.round_id;
    skipFrozen.value = isSkippedProgress(progress);
    taskProgress.value = progress;
  } catch (err) {
    if (version === bootstrapVersion.value) error.value = apiErrorMessage(err, "加载对话失败");
  }
}

async function useExample(question: string) {
  if (!inputEnabled.value || sending.value) return;
  draft.value = question;
  await send();
}

async function send() {
  const content = draft.value.trim();
  if (!content || !inputEnabled.value || !threadId.value) return;
  const clientMessageId = crypto.randomUUID();
  const requestVersion = ++latestRequestVersion.value;
  draft.value = "";
  error.value = "";
  activeRoundId.value = clientMessageId;
  skipFrozen.value = false;
  taskProgress.value = localThinkingProgress(clientMessageId);
  messages.value = [...messages.value, ...optimisticMessages(content, clientMessageId)];
  activeRequests.value += 1;
  try {
    const thread = await postMessage(threadId.value, content, clientMessageId, {
      onProgress: (progress) => applyStreamProgress(progress, clientMessageId),
      onToken: (delta) => applyStreamToken(delta, clientMessageId),
    });
    await applyThread(thread, clientMessageId, bootstrapVersion.value, requestVersion);
    applyProgressFromThread(thread);
  } catch (err) {
    messages.value = markRequestMessage(messages.value, clientMessageId, isTimeoutError(err) ? "timeout" : "error");
    if (!isTimeoutError(err)) error.value = apiErrorMessage(err, "发送失败");
  } finally {
    activeRequests.value -= 1;
  }
}

async function decideAndResume(approved: boolean, resumeBody: Record<string, unknown>) {
  if (!threadId.value) return;
  activeRequests.value += 1;
  error.value = "";
  try {
    if (hitl.value.approvalId) {
      await decideApproval(
        hitl.value.approvalId,
        approved,
        approved ? "用户在正式聊天批准" : "用户在正式聊天拒绝",
      );
    }
    const thread = await resumeThread(threadId.value, resumeBody, {
      onProgress: (progress) => applyStreamProgress(progress),
      onToken: (delta) => applyStreamToken(delta, ""),
    });
    await applyThread(thread);
    applyProgressFromThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, approved ? "审核失败" : "拒绝失败");
  } finally {
    activeRequests.value -= 1;
  }
}

async function onApprove(payload: { prompt: string; params: Record<string, unknown> }) {
  if (!threadId.value) return;
  if (!isMediaHitl()) {
    await decideAndResume(true, { action: "approve_once" });
    return;
  }
  activeRequests.value += 1;
  error.value = "";
  try {
    const thread = await resumeThread(threadId.value, approveResumePayload(payload.prompt, payload.params), {
      onProgress: (progress) => applyStreamProgress(progress),
      onToken: (delta) => applyStreamToken(delta, ""),
    });
    await applyThread(thread);
    applyProgressFromThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "审核失败");
  } finally {
    activeRequests.value -= 1;
  }
}

async function onSkip() {
  if (!threadId.value) return;
  skipFrozen.value = true;
  taskProgress.value = freezeSkipProgress(taskProgress.value, hitl.value.tool);
  activeRequests.value += 1;
  error.value = "";
  try {
    const thread = await resumeThread(threadId.value, skipResumePayload(), {
      onProgress: (progress) => applyStreamProgress(progress),
    });
    await applyThread(thread);
    applyProgressFromThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "跳过失败");
  } finally {
    activeRequests.value -= 1;
  }
}

async function onReject() {
  if (!threadId.value || isMediaHitl()) return;
  await decideAndResume(false, { action: "deny" });
}

async function logout() {
  await auth.logout();
  await router.replace({ name: "login" });
}

onMounted(bootstrap);
watch(agentInstanceId, bootstrap);
onUnmounted(() => {
  revokeAvatar();
  for (const url of blobUrls.values()) URL.revokeObjectURL(url);
});
</script>

<template>
  <div class="agent-page agent-chat">
    <header class="agent-chat-top">
      <div class="agent-chat-identity">
        <button class="agent-btn agent-btn-ghost" type="button" @click="router.push({ name: 'plaza' })">返回广场</button>
        <img v-if="avatarSrc" class="agent-avatar" :src="avatarSrc" alt="" />
        <div v-else class="agent-avatar-fallback">{{ title.slice(0, 1) }}</div>
        <strong>{{ title }}</strong>
      </div>
      <button class="agent-btn agent-btn-ghost" type="button" @click="logout">退出登录</button>
    </header>
    <div class="agent-chat-layout">
      <TaskProgressPanel :progress="taskProgress" />
      <section class="agent-chat-main">
        <p v-if="error" class="agent-error agent-chat-error">{{ error }}</p>
        <div class="agent-chat-body">
          <div class="agent-chat-column">
            <div class="agent-messages">
              <div v-if="!messages.length && !hitl.visible" class="agent-empty">
                <template v-if="showOfficialWelcome">
                  <p v-if="welcomeMessage">{{ welcomeMessage }}</p>
                  <p v-else>{{ EMPTY_CHAT_HINT }}</p>
                  <div v-if="exampleQuestions.length" class="agent-chat-examples">
                    <button
                      v-for="question in exampleQuestions"
                      :key="question"
                      class="agent-btn agent-btn-ghost"
                      type="button"
                      data-example-question
                      :disabled="!inputEnabled"
                      @click="useExample(question)"
                    >{{ question }}</button>
                  </div>
                </template>
                <template v-else>{{ EMPTY_CHAT_HINT }}</template>
              </div>
              <div
                v-for="(item, index) in messages"
                :key="item.messageId || item.clientMessageId || `${item.role}-${index}`"
                class="agent-msg-row"
                :class="{ 'is-user': item.role === 'user', 'is-pending': item.pending, 'is-timeout': item.status === 'timeout', 'is-error': item.status === 'error' }"
              >
                <div v-if="item.role !== 'user'" class="agent-msg-avatar" aria-hidden="true">
                  <img v-if="avatarSrc" class="agent-avatar" :src="avatarSrc" alt="" />
                  <div v-else class="agent-avatar-fallback">{{ title.slice(0, 1) }}</div>
                </div>
                <div class="agent-message-content">
                  <div v-if="item.createdAt" class="agent-message-time">{{ messageTime(item.createdAt) }}</div>
                  <div class="agent-bubble" :class="{ 'is-user': item.role === 'user', 'agent-bubble-pending': item.pending }" role="status" :aria-live="item.pending ? 'polite' : undefined">
                    <div v-if="bubbleText(item)">{{ bubbleText(item) }}</div>
                    <span v-if="item.pending" class="agent-typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>
                    <img v-for="preview in item.previews.filter((row) => row.widget === 'image')" :key="preview.url" class="agent-media" :src="preview.url" alt="" />
                    <video v-for="preview in item.previews.filter((row) => row.widget === 'video')" :key="preview.url" class="agent-media" :src="preview.url" controls />
                  </div>
                </div>
              </div>
              <div v-if="hitl.visible && !sending" class="agent-msg-row is-hitl">
                <div class="agent-msg-avatar" aria-hidden="true">
                  <img v-if="avatarSrc" class="agent-avatar" :src="avatarSrc" alt="" />
                  <div v-else class="agent-avatar-fallback">{{ title.slice(0, 1) }}</div>
                </div>
                <HitlCard
                  :visible="true"
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
            </div>
            <form class="agent-composer" @submit.prevent="send">
              <textarea v-model="draft" :disabled="!inputEnabled" placeholder="输入运营问题、提醒或内容需求" @keydown.enter.exact.prevent="send" />
              <button class="agent-btn" type="submit" :disabled="!inputEnabled">{{ sending ? "发送中..." : "发送" }}</button>
            </form>
          </div>
        </div>
      </section>
      <ChatSidebar :sidebar="sidebar" />
    </div>
  </div>
</template>
