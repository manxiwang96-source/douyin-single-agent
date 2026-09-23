import { CHAT_TIMEOUT_MS, authHeaders, clearSession, http, readToken, resolveApiBase } from "./http";
import { threadProgress, type TaskProgress } from "../lib/chat";
import { ChatHttpError } from "../lib/errors";

export type ChatStreamHandlers = {
  onProgress?: (progress: TaskProgress) => void;
  onToken?: (delta: string) => void;
};

function joinUrl(base: string, path: string): string {
  if (!base) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${base.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

function parseSseBlock(block: string): { event: string; data: string } | null {
  let eventName = "";
  const dataLines: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/^\uFEFF/, "");
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }
  if (!eventName && dataLines.length === 0) return null;
  return { event: eventName || "message", data: dataLines.join("\n") };
}

function takeSseBlocks(buffer: string): { blocks: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  return { blocks: parts, rest };
}

function parseJsonData(raw: string): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const name = (error as { name?: string }).name;
  const message = String((error as { message?: string }).message || "");
  return name === "AbortError" || /aborted|abort/i.test(message);
}

async function readJsonDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (payload && typeof payload === "object" && typeof (payload as { detail?: unknown }).detail === "string") {
      return (payload as { detail: string }).detail;
    }
  } catch {
    // Fall through to status text.
  }
  return response.statusText || "request failed";
}

async function consumeChatStream(response: Response, handlers?: ChatStreamHandlers): Promise<Record<string, unknown>> {
  if (!response.body) {
    throw new ChatHttpError(response.status, "missing chat stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let thread: Record<string, unknown> | null = null;
  let streamError: ChatHttpError | null = null;

  const handleBlock = (block: string) => {
    const parsed = parseSseBlock(block);
    if (!parsed) return;
    const payload = parseJsonData(parsed.data);
    if (parsed.event === "progress") {
      const raw = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
      handlers?.onProgress?.(threadProgress({ progress: raw }));
      return;
    }
    if (parsed.event === "token") {
      const delta = payload && typeof payload === "object" ? String((payload as { delta?: unknown }).delta || "") : "";
      if (delta) handlers?.onToken?.(delta);
      return;
    }
    if (parsed.event === "thread") {
      if (payload && typeof payload === "object") {
        thread = payload as Record<string, unknown>;
      }
      return;
    }
    if (parsed.event === "error") {
      const detail =
        payload && typeof payload === "object" && typeof (payload as { detail?: unknown }).detail === "string"
          ? (payload as { detail: string }).detail
          : "chat stream failed";
      streamError = new ChatHttpError(500, detail);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const taken = takeSseBlocks(buffer);
    buffer = taken.rest;
    for (const block of taken.blocks) handleBlock(block);
  }
  buffer += decoder.decode();
  if (buffer.trim()) {
    handleBlock(buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n"));
  }
  if (streamError) throw streamError;
  if (!thread) throw new ChatHttpError(response.status, "missing thread SSE event");
  return thread;
}

async function postChatSse(
  path: string,
  body: Record<string, unknown>,
  handlers?: ChatStreamHandlers,
): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  try {
    const response = await fetch(joinUrl(resolveApiBase(), path), {
      method: "POST",
      headers: {
        ...authHeaders(readToken()),
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (response.status === 401) {
      clearSession();
    }
    if (response.status !== 200) {
      throw new ChatHttpError(response.status, await readJsonDetail(response));
    }
    return await consumeChatStream(response, handlers);
  } catch (error) {
    if (error instanceof ChatHttpError) throw error;
    if (isAbortError(error) || controller.signal.aborted) {
      throw new ChatHttpError(0, "timeout", "ECONNABORTED");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export async function getThread(threadId: string): Promise<Record<string, unknown>> {
  const response = await http.get(`/v1/threads/${threadId}`);
  return response.data;
}

export async function postMessage(
  threadId: string,
  content: string,
  clientMessageId: string,
  handlers?: ChatStreamHandlers,
): Promise<Record<string, unknown>> {
  return postChatSse(
    `/v1/threads/${threadId}/messages`,
    { content, client_message_id: clientMessageId },
    handlers,
  );
}

export async function resumeThread(
  threadId: string,
  body: Record<string, unknown>,
  handlers?: ChatStreamHandlers,
): Promise<Record<string, unknown>> {
  return postChatSse(`/v1/threads/${threadId}/resume`, body, handlers);
}

export async function fetchAuthBlob(url: string): Promise<Blob> {
  const response = await http.get(url, { responseType: "blob" });
  return response.data;
}
