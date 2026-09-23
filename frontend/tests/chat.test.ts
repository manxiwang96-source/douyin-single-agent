import { describe, expect, it } from "vitest";
import {
  approveResumePayload,
  buildChatView,
  markRequestMessage,
  mergeChatMessages,
  messageTime,
  optimisticMessages,
  withPendingUser,
  emptyTaskProgress,
  freezeSkipProgress,
  interruptCard,
  isSkippedProgress,
  localThinkingProgress,
  shouldApplyTaskProgress,
  sidebarView,
  skipResumePayload,
  threadProgress,
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

  it("keeps server message time and does not invent old-message time", () => {
    const view = buildChatView({
      status: "idle",
      messages: [
        {
          role: "user",
          content: "带时间",
          media: [],
          message_id: "message-1",
          client_message_id: "client-1",
          created_at: "2026-09-23T12:34:56+08:00",
        },
        { role: "assistant", content: "旧消息", media: [] },
      ],
    });
    expect(view.messages[0].createdAt).toBe("2026-09-23T12:34:56+08:00");
    expect(messageTime(view.messages[0].createdAt)).toBe("2026-09-23 12:34:56");
    expect(view.messages[1].createdAt).toBeUndefined();
    expect(messageTime()).toBe("");
  });

  it("creates user-first optimistic and pending assistant messages with distinct ids", () => {
    const first = optimisticMessages("同样的文本", "client-1");
    const second = optimisticMessages("同样的文本", "client-2");
    expect(first.map((item) => item.role)).toEqual(["user", "assistant"]);
    expect(first[1].pending).toBe(true);
    expect(withPendingUser([], { content: "同样的文本", clientMessageId: "client-1", createdAt: "2026-09-23T12:00:00+08:00" })).toHaveLength(1);
    expect(withPendingUser(first, { content: "同样的文本", clientMessageId: "client-2", createdAt: "2026-09-23T12:00:01+08:00" })).toHaveLength(3);
    expect(second[0].clientMessageId).not.toBe(first[0].clientMessageId);
  });

  it("does not let an older server response erase newer local replies", () => {
    const newer = optimisticMessages("新消息", "client-new");
    newer[1] = { ...newer[1], content: "新回复", pending: false, status: "normal", messageId: "assistant-new" };
    const merged = mergeChatMessages(
      [{ role: "user", content: "旧消息", previews: [], messageId: "user-old" }],
      [
        { role: "user", content: "新消息", previews: [], clientMessageId: "client-new" },
        newer[1],
      ],
    );
    expect(merged.map((item) => item.content)).toEqual(["旧消息", "新消息", "新回复"]);
  });

  it("retains the user and visible assistant status after timeout or error", () => {
    const local = optimisticMessages("请求", "client-1");
    const timedOut = markRequestMessage(local, "client-1", "timeout");
    expect(timedOut).toHaveLength(2);
    expect(timedOut[0].content).toBe("请求");
    expect(timedOut[1].content).toContain("等待超时");
    expect(timedOut[1].status).toBe("timeout");
    const failed = markRequestMessage(local, "client-1", "error");
    expect(failed[0].content).toBe("请求");
    expect(failed[1].content).toContain("失败");
    expect(failed[1].status).toBe("error");
  });

});

describe("task progress helpers", () => {
  it("parses thread progress and defaults missing payload to idle", () => {
    expect(emptyTaskProgress()).toEqual({ round_id: null, phase: "idle", steps: [] });
    expect(threadProgress({})).toEqual({ round_id: null, phase: "idle", steps: [] });
    const parsed = threadProgress({
      progress: {
        round_id: "client-1",
        phase: "running",
        steps: [
          { id: "thinking", kind: "thinking", label: "正在思考", status: "done", spin: false },
          { id: "tool:search_kb:c1", kind: "tool", tool: "search_kb", label: "知识库检索", status: "running", spin: false },
        ],
      },
    });
    expect(parsed.phase).toBe("running");
    expect(parsed.steps[1].spin).toBe(true);
    expect(parsed.steps[1].label).toBe("知识库检索");
  });

  it("creates local thinking progress for a new user round", () => {
    const progress = localThinkingProgress("client-new");
    expect(progress).toEqual({
      round_id: "client-new",
      phase: "thinking",
      steps: [
        { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "running", spin: true },
      ],
    });
  });

  it("freezes skip progress as done without composing", () => {
    const frozen = freezeSkipProgress(
      {
        round_id: "client-1",
        phase: "waiting_review",
        steps: [
          { id: "thinking", kind: "thinking", tool: null, label: "正在思考", status: "done", spin: false },
          { id: "tool:generate_image:c1", kind: "review", tool: "generate_image", label: "等待审核「生成图片」", status: "waiting", spin: false },
          { id: "composing", kind: "composing", tool: null, label: "正在整理回复", status: "running", spin: true },
        ],
      },
      "generate_image",
    );
    expect(frozen.phase).toBe("done");
    expect(frozen.steps.map((step) => step.label)).toEqual(["正在思考", "已跳过「生成图片」"]);
    expect(frozen.steps.some((step) => step.kind === "composing")).toBe(false);
    expect(isSkippedProgress(frozen)).toBe(true);
  });

  it("ignores other-round and post-skip composing updates", () => {
    expect(
      shouldApplyTaskProgress(localThinkingProgress("client-2"), { activeRoundId: "client-1", skipFrozen: false }),
    ).toBe(false);
    expect(
      shouldApplyTaskProgress(
        { round_id: "client-1", phase: "composing", steps: [] },
        { activeRoundId: "client-1", skipFrozen: true },
      ),
    ).toBe(false);
    expect(
      shouldApplyTaskProgress(
        { round_id: null, phase: "idle", steps: [] },
        { activeRoundId: "client-1", skipFrozen: false },
      ),
    ).toBe(false);
    expect(
      shouldApplyTaskProgress(
        { round_id: "client-1", phase: "done", steps: [] },
        { activeRoundId: "client-1", skipFrozen: true },
      ),
    ).toBe(true);
  });
});
