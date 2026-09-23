import { describe, expect, it, vi } from "vitest";
import axios from "axios";
import { postMessage } from "../src/api/threads";

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

describe("http client", () => {
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


  it("uses the extended chat timeout and sends client identity", async () => {
    let requestData = "";
    chatHttp.defaults.adapter = async (config) => {
      requestData = String(config.data || "");
      return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
    };
    await expect(postMessage("thread-1", "你好", "client-1")).resolves.toEqual({ ok: true });
    expect(chatHttp.defaults.timeout).toBe(CHAT_TIMEOUT_MS);
    expect(JSON.parse(requestData)).toEqual({ content: "你好", client_message_id: "client-1" });
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
