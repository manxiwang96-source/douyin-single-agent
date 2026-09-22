import { describe, expect, it } from "vitest";
import {
  approveResumePayload,
  buildChatView,
  interruptCard,
  sidebarView,
  skipResumePayload,
} from "../src/lib/chat";

describe("chat helpers", () => {
  it("sidebar keeps catalog fields and omits model", () => {
    const view = sidebarView({
      title: "助手A",
      capability_description: "规划抖音运营并触达线索",
      development_notes: "能力只展示不勾选",
      agent_mode: "single",
      agent_mode_label: "单智能体模式",
      knowledge_documents: [{ title: "faq", filename: "faq.md" }],
      workflows: [{ code: "douyin-lead-discovery", display_name: "抖音线索发现与触达" }],
      tools: [
        {
          name: "discover_douyin_leads",
          display_name: "抖音线索发现",
          user_facing_summary: "扫描并真实发送评论或私信",
        },
      ],
      model: "should-not-appear",
    });
    expect(view.readonly).toBe(true);
    expect("model" in view).toBe(false);
    expect(view.capability_description).toContain("规划抖音运营");
    expect(view.development_notes).toContain("能力只展示");
    expect(view.knowledge_documents[0].filename).toBe("faq.md");
    expect(view.workflows[0].display_name).toBe("抖音线索发现与触达");
    expect(view.tools[0].name).toBe("discover_douyin_leads");
  });

  it("disables chat input during HITL", () => {
    const view = buildChatView({
      status: "interrupted",
      interrupt: {
        type: "review_media",
        tool: "generate_image",
        prompt: "bottle",
        params: { quality: "low" },
      },
      messages: [{ role: "user", content: "配图", media: [] }],
    });
    expect(view.chat_input_enabled).toBe(false);
    const card = interruptCard(view);
    expect(card.visible).toBe(true);
    expect(card.prompt).toBe("bottle");
    expect(approveResumePayload("bottle", { quality: "low" })).toEqual({
      action: "approve",
      prompt: "bottle",
      params: { quality: "low" },
    });
    expect(skipResumePayload()).toEqual({ action: "skip" });
  });
});
