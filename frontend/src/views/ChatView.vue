<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getAgentSidebar, openAgentInstance } from "../api/agents";
import { fetchAuthBlob, getThread, postMessage, resumeThread } from "../api/threads";
import ChatSidebar from "../components/ChatSidebar.vue";
import HitlCard from "../components/HitlCard.vue";
import {
  approveResumePayload,
  buildChatView,
  interruptCard,
  markRequestMessage,
  mergeChatMessages,
  messageTime,
  optimisticMessages,
  sidebarView,
  skipResumePayload,
  type ChatMessage,
  type SidebarView,
} from "../lib/chat";
import { apiErrorMessage } from "../lib/errors";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const agentInstanceId = computed(() => String(route.params.agentInstanceId || ""));
const threadId = ref(typeof route.query.thread_id === "string" ? route.query.thread_id : "");
const title = ref("抖音运营助手");
const avatarSrc = ref("");
const error = ref("");
const activeRequests = ref(0);
const sending = computed(() => activeRequests.value > 0);
const draft = ref("");
const messages = ref<ChatMessage[]>([]);
const inputEnabled = ref(true);
const hitl = ref({ visible: false, tool: null as unknown, prompt: "", params: {} as Record<string, unknown> });
const sidebar = ref<SidebarView>(sidebarView({}));
const bootstrapVersion = ref(0);
const latestRequestVersion = ref(0);
const blobUrls = new Map<string, string>();
let avatarObjectUrl = "";

function revokeAvatar() {
  if (avatarObjectUrl) {
    URL.revokeObjectURL(avatarObjectUrl);
    avatarObjectUrl = "";
  }
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

async function applyThread(thread: Record<string, unknown>, settledClientMessageId?: string, version = bootstrapVersion.value, requestVersion?: number) {
  const view = buildChatView(thread, "");
  const card = interruptCard(view);
  inputEnabled.value = view.chat_input_enabled;
  hitl.value = { visible: card.visible, tool: card.tool, prompt: card.prompt, params: card.params };
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
}

async function bootstrap() {
  const version = ++bootstrapVersion.value;
  error.value = "";
  try {
    const opened = await openAgentInstance(agentInstanceId.value);
    if (version !== bootstrapVersion.value) return;
    threadId.value = opened.thread_id;
    const [thread] = await Promise.all([getThread(opened.thread_id), loadSidebar()]);
    await applyThread(thread, undefined, version);
  } catch (err) {
    if (version === bootstrapVersion.value) error.value = apiErrorMessage(err, "加载对话失败");
  }
}

async function send() {
  const content = draft.value.trim();
  if (!content || !inputEnabled.value || !threadId.value) return;
  const clientMessageId = crypto.randomUUID();
  const requestVersion = ++latestRequestVersion.value;
  draft.value = "";
  error.value = "";
  messages.value = [...messages.value, ...optimisticMessages(content, clientMessageId)];
  activeRequests.value += 1;
  try {
    const thread = await postMessage(threadId.value, content, clientMessageId);
    await applyThread(thread, clientMessageId, bootstrapVersion.value, requestVersion);
  } catch (err) {
    messages.value = markRequestMessage(messages.value, clientMessageId, isTimeoutError(err) ? "timeout" : "error");
    if (!isTimeoutError(err)) error.value = apiErrorMessage(err, "发送失败");
  } finally {
    activeRequests.value -= 1;
  }
}

async function onApprove(payload: { prompt: string; params: Record<string, unknown> }) {
  if (!threadId.value) return;
  activeRequests.value += 1;
  error.value = "";
  try {
    const thread = await resumeThread(threadId.value, approveResumePayload(payload.prompt, payload.params));
    await applyThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "审核失败");
  } finally {
    activeRequests.value -= 1;
  }
}

async function onSkip() {
  if (!threadId.value) return;
  activeRequests.value += 1;
  error.value = "";
  try {
    const thread = await resumeThread(threadId.value, skipResumePayload());
    await applyThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "跳过失败");
  } finally {
    activeRequests.value -= 1;
  }
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
      <section class="agent-chat-main">
        <p v-if="error" class="agent-error agent-chat-error">{{ error }}</p>
        <div class="agent-chat-body">
          <div class="agent-chat-column">
            <div class="agent-messages">
              <div v-if="!messages.length && !hitl.visible" class="agent-empty">发送一条消息开始对话</div>
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
                    <div v-if="item.content">{{ item.content }}</div>
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
                <HitlCard :visible="true" :tool="hitl.tool" :prompt="hitl.prompt" :params="hitl.params" :disabled="sending" @approve="onApprove" @skip="onSkip" />
              </div>
            </div>
            <form class="agent-composer" @submit.prevent="send">
              <textarea v-model="draft" :disabled="!inputEnabled" placeholder="输入抖音运营问题、提醒或内容需求" @keydown.enter.exact.prevent="send" />
              <button class="agent-btn" type="submit" :disabled="!inputEnabled">{{ sending ? "发送中..." : "发送" }}</button>
            </form>
          </div>
        </div>
      </section>
      <ChatSidebar :sidebar="sidebar" />
    </div>
  </div>
</template>
