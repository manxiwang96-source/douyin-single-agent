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
  sidebarView,
  skipResumePayload,
  withPendingUser,
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
const sending = ref(false);
const draft = ref("");
const pendingUser = ref("");
const messages = ref<ChatMessage[]>([]);
const inputEnabled = ref(true);
const hitl = ref({ visible: false, tool: null as unknown, prompt: "", params: {} as Record<string, unknown> });
const sidebar = ref<SidebarView>(sidebarView({}));
const blobUrls = new Map<string, string>();
let avatarObjectUrl = "";

function revokeAvatar() {
  if (avatarObjectUrl) {
    URL.revokeObjectURL(avatarObjectUrl);
    avatarObjectUrl = "";
  }
}

async function resolvePreview(url: string): Promise<string> {
  if (blobUrls.has(url)) {
    return blobUrls.get(url) || url;
  }
  try {
    const blob = await fetchAuthBlob(url);
    const objectUrl = URL.createObjectURL(blob);
    blobUrls.set(url, objectUrl);
    return objectUrl;
  } catch {
    return url;
  }
}

async function applyThread(thread: Record<string, unknown>) {
  const view = buildChatView(thread, "");
  const card = interruptCard(view);
  inputEnabled.value = view.chat_input_enabled;
  hitl.value = {
    visible: card.visible,
    tool: card.tool,
    prompt: card.prompt,
    params: card.params,
  };
  const nextMessages: ChatMessage[] = [];
  for (const item of withPendingUser(view.messages, pendingUser.value)) {
    const previews = [];
    for (const preview of item.previews) {
      previews.push({ widget: preview.widget, url: await resolvePreview(preview.url) });
    }
    nextMessages.push({ ...item, previews });
  }
  messages.value = nextMessages;
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
  error.value = "";
  try {
    const opened = await openAgentInstance(agentInstanceId.value);
    threadId.value = opened.thread_id;
    await Promise.all([
      loadSidebar(),
      getThread(opened.thread_id).then(applyThread),
    ]);
  } catch (err) {
    error.value = apiErrorMessage(err, "加载对话失败");
  }
}

async function send() {
  const content = draft.value.trim();
  if (!content || !inputEnabled.value || sending.value || !threadId.value) {
    return;
  }
  draft.value = "";
  pendingUser.value = content;
  sending.value = true;
  error.value = "";
  messages.value = withPendingUser(messages.value, content);
  try {
    const thread = await postMessage(threadId.value, content);
    pendingUser.value = "";
    await applyThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "发送失败");
  } finally {
    sending.value = false;
  }
}

async function onApprove(payload: { prompt: string; params: Record<string, unknown> }) {
  if (!threadId.value) {
    return;
  }
  sending.value = true;
  error.value = "";
  try {
    const thread = await resumeThread(threadId.value, approveResumePayload(payload.prompt, payload.params));
    await applyThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "审核失败");
  } finally {
    sending.value = false;
  }
}

async function onSkip() {
  if (!threadId.value) {
    return;
  }
  sending.value = true;
  error.value = "";
  try {
    const thread = await resumeThread(threadId.value, skipResumePayload());
    await applyThread(thread);
  } catch (err) {
    error.value = apiErrorMessage(err, "跳过失败");
  } finally {
    sending.value = false;
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
  for (const url of blobUrls.values()) {
    URL.revokeObjectURL(url);
  }
});
</script>

<template>
  <div class="agent-page agent-chat">
    <section class="agent-chat-main">
      <header class="agent-chat-top">
        <div class="agent-chat-identity">
          <button class="agent-btn agent-btn-ghost" type="button" @click="router.push({ name: 'plaza' })">返回广场</button>
          <img v-if="avatarSrc" class="agent-avatar" :src="avatarSrc" alt="" />
          <div v-else class="agent-avatar-fallback">{{ title.slice(0, 1) }}</div>
          <strong>{{ title }}</strong>
        </div>
        <button class="agent-btn agent-btn-ghost" type="button" @click="logout">退出登录</button>
      </header>
      <p v-if="error" class="agent-error" style="padding: 0 20px;">{{ error }}</p>
      <HitlCard
        :visible="hitl.visible"
        :tool="hitl.tool"
        :prompt="hitl.prompt"
        :params="hitl.params"
        :disabled="sending"
        @approve="onApprove"
        @skip="onSkip"
      />
      <div class="agent-messages">
        <div v-for="(item, index) in messages" :key="index" class="agent-bubble" :class="{ 'is-user': item.role === 'user' }">
          <div v-if="item.content">{{ item.content }}</div>
          <img
            v-for="preview in item.previews.filter((row) => row.widget === 'image')"
            :key="preview.url"
            class="agent-media"
            :src="preview.url"
            alt=""
          />
          <video
            v-for="preview in item.previews.filter((row) => row.widget === 'video')"
            :key="preview.url"
            class="agent-media"
            :src="preview.url"
            controls
          />
        </div>
      </div>
      <form class="agent-composer" @submit.prevent="send">
        <textarea
          v-model="draft"
          :disabled="!inputEnabled || sending"
          placeholder="输入抖音运营问题、提醒或内容需求"
          @keydown.enter.exact.prevent="send"
        />
        <button class="agent-btn" type="submit" :disabled="!inputEnabled || sending">
          {{ sending ? "发送中..." : "发送" }}
        </button>
      </form>
    </section>
    <ChatSidebar :sidebar="sidebar" />
  </div>
</template>
