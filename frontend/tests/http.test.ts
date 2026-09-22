import { describe, expect, it, vi } from "vitest";
import axios from "axios";
import {
  HTTP_TIMEOUT_MS,
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
