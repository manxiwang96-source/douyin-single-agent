import { describe, expect, it } from "vitest";
import { apiErrorMessage } from "../src/lib/errors";
import {
  createInstancePayload,
  filterCards,
  mapPlazaCards,
  patchInstancePayload,
} from "../src/lib/plaza";
import { validateTitle } from "../src/lib/title";
import axios from "axios";

function axiosError(detail: string, status: number) {
  const error = {
    isAxiosError: true,
    response: { data: { detail }, status },
    toJSON: () => ({}),
    name: "AxiosError",
    message: String(status),
  };
  Object.setPrototypeOf(error, axios.AxiosError.prototype);
  return error;
}

describe("plaza helpers", () => {
  it("locks create payload to douyin_ops", () => {
    const payload = createInstancePayload("助手A", "简介", "data:image/png;base64,xx");
    expect(payload.template_code).toBe("douyin_ops");
    expect(payload.title).toBe("助手A");
    expect(payload.intro).toBe("简介");
    expect(payload.avatar).toBe("data:image/png;base64,xx");
    expect(Object.keys(payload).sort()).toEqual(["avatar", "intro", "template_code", "title"]);
  });

  it("omits avatar from patch payload unless a new image is provided", () => {
    expect(Object.keys(patchInstancePayload("助手A", "简介")).sort()).toEqual(["intro", "title"]);
    expect(Object.keys(patchInstancePayload("助手A", "简介", null)).sort()).toEqual(["intro", "title"]);
    expect(Object.keys(patchInstancePayload("助手A", "简介", "")).sort()).toEqual(["intro", "title"]);
    const withAvatar = patchInstancePayload("助手A", "简介", "data:image/png;base64,xx");
    expect(withAvatar.avatar).toBe("data:image/png;base64,xx");
    expect(Object.keys(withAvatar).sort()).toEqual(["avatar", "intro", "title"]);
    expect(withAvatar).not.toHaveProperty("template_code");
  });

  it("rejects blank or whitespace titles", () => {
    expect(() => validateTitle("   ")).toThrow("名称不能为空");
    expect(() => validateTitle("我的 助手")).toThrow("名称不能包含空白字符");
  });

  it("maps card fields and filters locally", () => {
    const cards = mapPlazaCards([
      {
        agent_instance_id: "id-1",
        title: "助手A",
        intro: "日常运营",
        avatar_url: "/v1/agent-instances/id-1/avatar",
        agent_mode: "single",
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-02T00:00:00",
      },
    ]);
    expect(cards[0].agent_mode_label).toBe("单智能体模式");
    expect(cards[0].created_at).toBe("2026-01-01T00:00:00");
    expect(cards[0].updated_at).toBe("2026-01-02T00:00:00");
    expect(filterCards(cards, "运营")).toHaveLength(1);
    expect(filterCards(cards, "不存在")).toHaveLength(0);
  });

  it("maps title already in use to Chinese copy", () => {
    expect(apiErrorMessage(axiosError("title already in use", 409))).toBe("名称已被使用");
  });

  it("maps archived instance 404 to Chinese copy", () => {
    expect(apiErrorMessage(axiosError("agent instance not found", 404))).toBe("该智能体不存在或已归档");
  });
});
