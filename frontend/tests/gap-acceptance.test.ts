import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DISCOVER_LEADS_TOOL_CODE, resolveToolCode } from "../src/api/agentConfig";
import { publishedChatWelcome, shouldShowOfficialWelcome } from "../src/lib/chat";
import { createInstancePayload, isCustomTemplateCode } from "../src/lib/plaza";

describe("W35 custom agent gap acceptance", () => {
  it("creates custom payloads without changing ops default", () => {
    expect(createInstancePayload("助手A", "简介", null).template_code).toBe("douyin_ops");
    expect(createInstancePayload("自定义", "说明", null, "custom")).toMatchObject({
      template_code: "custom",
      title: "自定义",
    });
    expect(isCustomTemplateCode("custom")).toBe(true);
    expect(isCustomTemplateCode("douyin_ops")).toBe(false);
  });

  it("resolves legacy leads alias to discover_leads", () => {
    expect(DISCOVER_LEADS_TOOL_CODE).toBe("discover_leads");
    expect(resolveToolCode("discover_douyin_leads")).toBe("discover_leads");
    expect(resolveToolCode("discover_leads")).toBe("discover_leads");
  });

  it("shows published welcome only on empty official chat", () => {
    expect(
      publishedChatWelcome({
        items: [
          { status: "draft", version_no: 2, welcome_message: "draft-welcome", example_questions: ["draft-q"] },
          { status: "published", version_no: 1, welcome_message: "published-welcome", example_questions: ["published-q"] },
        ],
      }),
    ).toEqual({ welcomeMessage: "published-welcome", exampleQuestions: ["published-q"] });
    expect(shouldShowOfficialWelcome({ threadKind: "official", messageCount: 0 })).toBe(true);
    expect(shouldShowOfficialWelcome({ threadKind: "debug", messageCount: 0 })).toBe(false);
    expect(shouldShowOfficialWelcome({ threadKind: "official", messageCount: 1 })).toBe(false);
  });

  it("locks plaza custom routing and draft debug SSE sources", () => {
    const plaza = readFileSync(resolve(process.cwd(), "src/views/PlazaView.vue"), "utf-8");
    expect(plaza).toContain("isCustomTemplateCode");
    expect(plaza).toContain('name: "agent-config"');
    expect(plaza).toContain("loadCards()");

    const debugPane = readFileSync(
      resolve(process.cwd(), "src/components/agent-config/AgentConfigDebugPane.vue"),
      "utf-8",
    );
    expect(debugPane).toContain("openDebugThread");
    expect(debugPane).toContain("postMessage");
    expect(debugPane).toContain("resumeThread");
    expect(debugPane).toContain("真实执行");
    expect(debugPane).not.toContain("previewAgentDraft");

    const layout = readFileSync(resolve(process.cwd(), "src/views/AgentConfigView.vue"), "utf-8");
    expect(layout).toContain("AgentConfigTopbar");
    expect(layout).toContain("AgentConfigNav");
    expect(layout).toContain("AgentConfigDebugPane");
  });
});
