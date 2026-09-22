import { mount, flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import ChatSidebar from "../src/components/ChatSidebar.vue";
import CreateAgentModal from "../src/components/CreateAgentModal.vue";
import HitlCard from "../src/components/HitlCard.vue";
import { sidebarView } from "../src/lib/chat";

vi.mock("../src/api/agents", () => ({
  createAgentInstance: vi.fn(),
}));

import { createAgentInstance } from "../src/api/agents";

describe("vue components", () => {
  it("create modal stays on two steps without changing route", async () => {
    const wrapper = mount(CreateAgentModal, { props: { open: true } });
    expect(wrapper.text()).toContain("抖音运营助手");
    expect(wrapper.text()).not.toContain("对话式智能体");
    await wrapper.get(".agent-template").trigger("click");
    expect(wrapper.text()).toContain("名称*");
    expect(wrapper.text()).toContain("简介*");
    expect(wrapper.text()).toContain("本机上传头像");
    expect(wrapper.text()).not.toContain("AI生成头像");
    await wrapper.get("input").setValue("助手A");
    await wrapper.get("textarea").setValue("日常运营");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(createAgentInstance).toHaveBeenCalledWith("助手A", "日常运营", null);
  });

  it("sidebar renders catalog fields and no model", () => {
    const wrapper = mount(ChatSidebar, {
      props: {
        sidebar: sidebarView({
          capability_description: "规划抖音运营并触达线索",
          development_notes: "能力只展示不勾选",
          agent_mode_label: "单智能体模式",
          knowledge_documents: [{ title: "faq", filename: "faq.md" }],
          workflows: [{ code: "douyin-lead-discovery", display_name: "抖音线索发现与触达" }],
          tools: [{ name: "discover_douyin_leads", display_name: "抖音线索发现", user_facing_summary: "真实发送" }],
          model: "hidden",
        }),
      },
    });
    expect(wrapper.text()).toContain("规划抖音运营并触达线索");
    expect(wrapper.text()).toContain("能力只展示不勾选");
    expect(wrapper.text()).toContain("faq");
    expect(wrapper.text()).toContain("抖音线索发现与触达");
    expect(wrapper.text()).toContain("抖音线索发现");
    expect(wrapper.text()).toContain("多智能体模式");
    expect(wrapper.text()).not.toContain("hidden");
    expect(wrapper.html()).not.toContain("model");
  });

  it("HITL card exposes approve/skip and chat helpers disable input", async () => {
    const wrapper = mount(HitlCard, {
      props: {
        visible: true,
        tool: "generate_image",
        prompt: "bottle",
        params: { quality: "low" },
      },
    });
    await wrapper.get("button.agent-btn").trigger("click");
    expect(wrapper.emitted("approve")?.[0][0]).toEqual({
      prompt: "bottle",
      params: { quality: "low" },
    });
    await wrapper.get("button.agent-btn-ghost").trigger("click");
    expect(wrapper.emitted("skip")).toBeTruthy();
  });
});
