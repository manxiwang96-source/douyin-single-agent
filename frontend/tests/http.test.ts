import { afterEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import { postMessage, resumeThread } from "../src/api/threads";
import { ChatHttpError } from "../src/lib/errors";

import {
  CHAT_TIMEOUT_MS,
  HTTP_TIMEOUT_MS,
  chatHttp,
  authHeaders,
  clearSession,
  createHttpClient,
  memoryStorage,
  readToken,
  writeSession,
} from "../src/api/http";

function sseBody(events: Array<{ event: string; data: string }>, newline = "\n"): string {
  return events.map((item) => `event: ${item.event}${newline}data: ${item.data}${newline}${newline}`).join("");
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sseResponse(body: string, status = 200) {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}


function lastFetchCall(fetchMock: ReturnType<typeof vi.fn>): [string, RequestInit & { headers: Record<string, string> }] {
  const call = fetchMock.mock.calls[0] as [string, RequestInit] | undefined;
  if (!call) {
    throw new Error("fetch was not called");
  }
  const [url, init] = call;
  return [url, { ...init, headers: (init.headers || {}) as Record<string, string> }];
}

describe("http client", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("puts bearer token on requests", async () => {
    const storage = memoryStorage({ token: "abc123" });
    const client = createHttpClient({ storage, baseURL: "http://example.test" });
    client.defaults.adapter = async (config) => ({
      data: {},
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    });
    const response = await client.get("/v1/me");
    expect(response.config.headers.Authorization).toBe("Bearer abc123");
    expect(authHeaders("abc123")).toEqual({ Authorization: "Bearer abc123" });
    expect(client.defaults.timeout).toBe(HTTP_TIMEOUT_MS);
  });

  it("posts chat messages with fetch SSE instead of EventSource", async () => {
    localStorage.setItem("token", "abc123");
    const fetchMock = vi.fn(async () =>
      sseResponse(sseBody([{ event: "thread", data: JSON.stringify({ ok: true, messages: [] }) }])),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onProgress = vi.fn();
    const onToken = vi.fn();
    await expect(postMessage("thread-1", "你好", "client-1", { onProgress, onToken })).resolves.toEqual({
      ok: true,
      messages: [],
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = lastFetchCall(fetchMock);
    expect(String(url)).toContain("/v1/threads/thread-1/messages");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer abc123");
    expect(init.headers.Accept).toBe("text/event-stream");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({ content: "你好", client_message_id: "client-1" });
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(fetchMock).toHaveBeenCalled();
    expect(chatHttp.defaults.timeout).toBe(CHAT_TIMEOUT_MS);
  });

  it("parses CRLF SSE progress and token before resolving thread", async () => {
    localStorage.setItem("token", "tok");
    const body = sseBody(
      [
        { event: "progress", data: JSON.stringify({ round_id: "client-1", phase: "thinking", steps: [] }) },
        { event: "token", data: JSON.stringify({ delta: "你好" }) },
        { event: "thread", data: JSON.stringify({ ok: true }) },
      ],
      "\r\n",
    );
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse(body)));
    const onProgress = vi.fn();
    const onToken = vi.fn();
    await expect(postMessage("thread-1", "你好", "client-1", { onProgress, onToken })).resolves.toEqual({ ok: true });
    expect(onProgress).toHaveBeenCalledWith({ round_id: "client-1", phase: "thinking", steps: [] });
    expect(onToken).toHaveBeenCalledWith("你好");
  });

  it("resumes threads with fetch and rejects JSON 409 without parsing SSE", async () => {
    localStorage.setItem("token", "tok");
    const fetchMock = vi.fn(async () => jsonResponse(409, { detail: "thread is not waiting for review" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(resumeThread("thread-1", { action: "approve" })).rejects.toMatchObject({
      status: 409,
      detail: "thread is not waiting for review",
    });
    const [url, init] = lastFetchCall(fetchMock);
    expect(String(url)).toContain("/v1/threads/thread-1/resume");
    expect(init.headers.Accept).toBe("text/event-stream");
  });

  it("clears session on chat 401", async () => {
    localStorage.setItem("token", "abc123");
    localStorage.setItem("user_id", "u1");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { detail: "not authenticated" })));
    await expect(postMessage("thread-1", "你好", "client-1")).rejects.toBeInstanceOf(ChatHttpError);
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("aborts chat fetch after CHAT_TIMEOUT_MS", async () => {
    vi.useFakeTimers();
    localStorage.setItem("token", "tok");
    const fetchMock = vi.fn((_url: string, init: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const pending = expect(postMessage("thread-1", "你好", "client-1")).rejects.toMatchObject({
      code: "ECONNABORTED",
    });
    await vi.advanceTimersByTimeAsync(CHAT_TIMEOUT_MS);
    await pending;
  });

  it("clears session on 401", async () => {
    const storage = memoryStorage({ token: "abc123", user_id: "u1", login_name: "alice" });
    const onUnauthorized = vi.fn();
    const client = createHttpClient({ storage, onUnauthorized, baseURL: "http://example.test" });
    client.defaults.adapter = async (config) => {
      throw new axios.AxiosError(
        "not authenticated",
        "ERR_BAD_REQUEST",
        config,
        null,
        {
          data: { detail: "not authenticated" },
          status: 401,
          statusText: "Unauthorized",
          headers: {},
          config,
        },
      );
    };
    await expect(client.get("/v1/agent-instances")).rejects.toBeTruthy();
    expect(readToken(storage)).toBe("");
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("writes and clears session storage", () => {
    const storage = memoryStorage();
    writeSession({ token: "t", user_id: "u", login_name: "a" }, storage);
    expect(readToken(storage)).toBe("t");
    clearSession(storage);
    expect(readToken(storage)).toBe("");
  });
});
