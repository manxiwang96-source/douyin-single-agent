export type ChatPreview = { widget: "image" | "video"; url: string };
export type ChatMessage = {
  role: string;
  content: string;
  previews: ChatPreview[];
};

export function absoluteMediaUrl(apiBase: string, url: string): string {
  if (!url) {
    return "";
  }
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  const base = apiBase.replace(/\/$/, "");
  return `${base}${url.startsWith("/") ? url : `/${url}`}`;
}

export function messagePreviews(
  message: Record<string, unknown>,
  apiBase: string,
): ChatPreview[] {
  const previews: ChatPreview[] = [];
  for (const item of (message.media as Array<Record<string, unknown>> | undefined) || []) {
    const kind = item.type;
    const url = absoluteMediaUrl(apiBase, String(item.url || ""));
    if (kind === "image" && url) {
      previews.push({ widget: "image", url });
    } else if (kind === "video" && url) {
      previews.push({ widget: "video", url });
    }
  }
  return previews;
}

export function buildChatView(thread: Record<string, unknown>, apiBase = ""): {
  messages: ChatMessage[];
  interrupt: Record<string, unknown> | null;
  chat_input_enabled: boolean;
} {
  const messages = ((thread.messages as Array<Record<string, unknown>>) || []).map((item) => ({
    role: String(item.role || ""),
    content: String(item.content || ""),
    previews: messagePreviews(item, apiBase),
  }));
  const pending = (thread.interrupt as Record<string, unknown> | null) || null;
  const interrupted = thread.status === "interrupted" || Boolean(pending);
  return {
    messages,
    interrupt: pending,
    chat_input_enabled: !interrupted,
  };
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

export function withPendingUser(messages: ChatMessage[], pending: string | null | undefined): ChatMessage[] {
  const text = (pending || "").trim();
  if (!text) {
    return [...messages];
  }
  if (messages.some((item) => item.role === "user" && item.content === text)) {
    return [...messages];
  }
  return [...messages, { role: "user", content: text, previews: [] }];
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
    agent_mode_label:
      String(data.agent_mode_label || "") ||
      ((data.agent_mode || "single") === "single" ? "单智能体模式" : "多智能体模式"),
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
