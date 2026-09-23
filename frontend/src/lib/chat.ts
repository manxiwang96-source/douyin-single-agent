export type ChatPreview = { widget: "image" | "video"; url: string };
export type ChatMessageStatus = "pending" | "timeout" | "error" | "normal";
export type ChatMessage = {
  role: string;
  content: string;
  previews: ChatPreview[];
  messageId?: string;
  clientMessageId?: string;
  createdAt?: string;
  pending?: boolean;
  error?: string;
  status?: ChatMessageStatus;
  requestId?: string;
};

export function absoluteMediaUrl(apiBase: string, url: string): string {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  const base = apiBase.replace(/\/$/, "");
  return `${base}${url.startsWith("/") ? url : `/${url}`}`;
}

export function messagePreviews(message: Record<string, unknown>, apiBase: string): ChatPreview[] {
  const previews: ChatPreview[] = [];
  for (const item of (message.media as Array<Record<string, unknown>> | undefined) || []) {
    const kind = item.type;
    const url = absoluteMediaUrl(apiBase, String(item.url || ""));
    if (kind === "image" && url) previews.push({ widget: "image", url });
    else if (kind === "video" && url) previews.push({ widget: "video", url });
  }
  return previews;
}

function mapMessage(item: Record<string, unknown>, apiBase: string): ChatMessage {
  const status = String(item.status || "normal") as ChatMessageStatus;
  return {
    role: String(item.role || ""),
    content: String(item.content || ""),
    previews: messagePreviews(item, apiBase),
    messageId: item.message_id ? String(item.message_id) : undefined,
    clientMessageId: item.client_message_id ? String(item.client_message_id) : undefined,
    createdAt: item.created_at ? String(item.created_at) : undefined,
    pending: Boolean(item.pending),
    error: item.error ? String(item.error) : undefined,
    status,
  };
}

export function buildChatView(thread: Record<string, unknown>, apiBase = ""): {
  messages: ChatMessage[];
  interrupt: Record<string, unknown> | null;
  chat_input_enabled: boolean;
} {
  const messages = ((thread.messages as Array<Record<string, unknown>>) || []).map((item) => mapMessage(item, apiBase));
  const pending = (thread.interrupt as Record<string, unknown> | null) || null;
  const interrupted = thread.status === "interrupted" || Boolean(pending);
  return { messages, interrupt: pending, chat_input_enabled: !interrupted };
}

export function messageTime(createdAt?: string): string {
  if (!createdAt) return "";
  // Keep the date/time represented by the server instead of converting it to
  // the browser timezone. The backend's offset is part of the authority.
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/.exec(createdAt);
  if (match) return `${match[1]} ${match[2]}`;
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function optimisticMessages(content: string, clientMessageId: string, createdAt?: string): ChatMessage[] {
  return [
    { role: "user", content, previews: [], clientMessageId, createdAt, status: "normal" },
    {
      role: "assistant",
      content: "正在回复",
      previews: [],
      clientMessageId,
      requestId: clientMessageId,
      pending: true,
      status: "pending",
    },
  ];
}

export function withPendingUser(messages: ChatMessage[], pending: { content: string; clientMessageId: string; createdAt: string } | null | undefined): ChatMessage[] {
  if (!pending?.content.trim()) return [...messages];
  if (messages.some((item) => item.clientMessageId === pending.clientMessageId)) return [...messages];
  return [...messages, optimisticMessages(pending.content.trim(), pending.clientMessageId, pending.createdAt)[0]];
}

export function mergeChatMessages(server: ChatMessage[], local: ChatMessage[], settledClientMessageId?: string): ChatMessage[] {
  const serverMessageIds = new Set(server.map((item) => item.messageId).filter(Boolean));
  const serverClientIds = new Set(server.map((item) => item.clientMessageId).filter(Boolean));
  const pendingLocal = local.filter((item) => {
    if (item.messageId && serverMessageIds.has(item.messageId)) return false;
    if (item.clientMessageId && serverClientIds.has(item.clientMessageId)) return false;
    // A delayed response may contain an older checkpoint. Preserve every local
    // message with a client id so newer settled replies cannot disappear.
    if (item.clientMessageId) return true;
    return item.pending || item.role === "user" || (settledClientMessageId === item.clientMessageId && (item.status === "timeout" || item.status === "error"));
  });
  const result = [...server];
  for (const localMessage of pendingLocal) {
    if (localMessage.pending) {
      const match = result.findIndex((item) => item.clientMessageId && item.clientMessageId === localMessage.clientMessageId);
      if (match >= 0) continue;
    }
    if (localMessage.role === "user") {
      const userIndex = result.findIndex(
        (item) => item.role === "user" && item.clientMessageId === localMessage.clientMessageId,
      );
      if (userIndex >= 0) continue;
    }
    result.push(localMessage);
  }
  return result;
}

export function markRequestMessage(messages: ChatMessage[], clientMessageId: string, status: "timeout" | "error"): ChatMessage[] {
  return messages.map((item) => {
    if (item.clientMessageId !== clientMessageId || !item.pending) return item;
    return {
      ...item,
      pending: false,
      status,
      content: status === "timeout" ? "等待超时，后台可能仍在处理" : "本次回复失败，请重试",
      error: status === "timeout" ? "后台可能仍在处理" : "请重试",
    };
  });
}

export function interruptCard(view: { interrupt?: Record<string, unknown> | null }): {
  visible: boolean;
  tool: unknown;
  prompt: string;
  params: Record<string, unknown>;
} {
  const pending = view.interrupt || {};
  const visible = Boolean(view.interrupt);
  return {
    visible,
    tool: visible ? pending.tool : null,
    prompt: visible ? String(pending.prompt || "") : "",
    params: visible ? ((pending.params as Record<string, unknown>) || {}) : {},
  };
}

export type SidebarView = {
  title: string;
  intro: string;
  capability_description: string;
  development_notes: string;
  agent_mode: string;
  agent_mode_label: string;
  knowledge_documents: Array<Record<string, unknown>>;
  workflows: Array<Record<string, unknown>>;
  tools: Array<Record<string, unknown>>;
  readonly: true;
};

export function sidebarView(payload: Record<string, unknown> | null | undefined): SidebarView {
  const data = payload || {};
  return {
    title: String(data.title || ""),
    intro: String(data.intro || ""),
    capability_description: String(data.capability_description || ""),
    development_notes: String(data.development_notes || ""),
    agent_mode: String(data.agent_mode || "single"),
    agent_mode_label: String(data.agent_mode_label || "") || ((data.agent_mode || "single") === "single" ? "单智能体模式" : "多智能体模式"),
    knowledge_documents: Array.isArray(data.knowledge_documents) ? [...data.knowledge_documents as Array<Record<string, unknown>>] : [],
    workflows: Array.isArray(data.workflows) ? [...data.workflows as Array<Record<string, unknown>>] : [],
    tools: Array.isArray(data.tools) ? [...data.tools as Array<Record<string, unknown>>] : [],
    readonly: true,
  };
}

export function approveResumePayload(prompt: string, params: Record<string, unknown>): Record<string, unknown> {
  return { action: "approve", prompt, params };
}

export function skipResumePayload(): Record<string, string> {
  return { action: "skip" };
}

export type TaskStepStatus = "done" | "running" | "waiting";
export type TaskStepKind = "thinking" | "tool" | "review" | "composing";
export type TaskPhase = "idle" | "thinking" | "running" | "waiting_review" | "composing" | "done";

export type TaskStep = {
  id: string;
  kind: TaskStepKind;
  tool: string | null;
  label: string;
  status: TaskStepStatus;
  spin: boolean;
};

export type TaskProgress = {
  round_id: string | null;
  phase: TaskPhase;
  steps: TaskStep[];
};

export function emptyTaskProgress(): TaskProgress {
  return { round_id: null, phase: "idle", steps: [] };
}

export function localThinkingProgress(roundId: string): TaskProgress {
  return {
    round_id: roundId,
    phase: "thinking",
    steps: [
      {
        id: "thinking",
        kind: "thinking",
        tool: null,
        label: '正在思考',
        status: "running",
        spin: true,
      },
    ],
  };
}

function parseStep(item: Record<string, unknown>): TaskStep {
  const status = String(item.status || "running") as TaskStepStatus;
  return {
    id: String(item.id || ""),
    kind: String(item.kind || "tool") as TaskStepKind,
    tool: item.tool == null || item.tool === "" ? null : String(item.tool),
    label: String(item.label || ""),
    status,
    spin: status === "running",
  };
}

export function threadProgress(thread: Record<string, unknown> | null | undefined): TaskProgress {
  const raw = (thread?.progress as Record<string, unknown> | undefined) || undefined;
  if (!raw || typeof raw !== "object") return emptyTaskProgress();
  const phaseRaw = String(raw.phase || "idle") as TaskPhase;
  const allowed: TaskPhase[] = ["idle", "thinking", "running", "waiting_review", "composing", "done"];
  const phase = allowed.includes(phaseRaw) ? phaseRaw : "idle";
  const steps = Array.isArray(raw.steps)
    ? (raw.steps as Array<Record<string, unknown>>).map(parseStep).filter((step) => step.id || step.label)
    : [];
  const roundId = raw.round_id == null || raw.round_id === "" ? null : String(raw.round_id);
  return { round_id: roundId, phase, steps };
}

export function skippedMediaLabel(tool: unknown): string {
  return tool === "generate_video" ? '已跳过「生成视频」' : '已跳过「生成图片」';
}

export function freezeSkipProgress(progress: TaskProgress, tool?: unknown): TaskProgress {
  const label = skippedMediaLabel(tool);
  const toolName = typeof tool === "string" && tool ? tool : "generate_image";
  let found = false;
  const steps = progress.steps
    .filter((step) => step.kind !== "composing")
    .map((step) => {
      const isTarget =
        step.status === "waiting" ||
        step.kind === "review" ||
        step.tool === toolName ||
        ((step.tool === "generate_image" || step.tool === "generate_video") && step.status !== "done");
      if (!isTarget) {
        return { ...step, status: step.status === "running" ? ("done" as const) : step.status, spin: false };
      }
      found = true;
      return { ...step, kind: "review" as const, label, status: "done" as const, spin: false };
    });
  if (!found) {
    steps.push({
      id: `review:${toolName}`,
      kind: "review",
      tool: toolName,
      label,
      status: "done",
      spin: false,
    });
  }
  return { round_id: progress.round_id, phase: "done", steps };
}

export function shouldApplyTaskProgress(
  incoming: TaskProgress,
  options: { activeRoundId: string | null; skipFrozen: boolean },
): boolean {
  if (options.skipFrozen && incoming.phase !== "done") return false;
  if (options.activeRoundId) {
    if (incoming.round_id && incoming.round_id !== options.activeRoundId) return false;
    if (!incoming.round_id && (incoming.phase === "idle" || incoming.steps.length === 0)) return false;
  }
  return true;
}

export function isSkippedProgress(progress: TaskProgress): boolean {
  return progress.phase === "done" && progress.steps.some((step) => step.label.startsWith('已跳过'));
}
