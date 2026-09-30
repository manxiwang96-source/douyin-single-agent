export const DOUYIN_TEMPLATE_CODE = "douyin_ops";
export const CUSTOM_TEMPLATE_CODE = "custom";

export const CUSTOM_TEMPLATE = {
  template_code: CUSTOM_TEMPLATE_CODE,
  title: "自定义智能体",
  description: "按你的提示词、知识库、Skill、工具和工作流配置专属智能体，默认仅启用当前时间工具。",
};

export const DOUYIN_TEMPLATE = {
  template_code: DOUYIN_TEMPLATE_CODE,
  title: "运营助手",
  description: "围绕抖音和小红书账号、话题及内容做运营规划，并通过已绑定工作流做线索发现与真实触达",
};

export type AgentCard = {
  agent_instance_id: string;
  title: string;
  intro: string;
  avatar_url: string | null;
  template_code: string;
  agent_mode: string;
  agent_mode_label: string;
  created_at: string | null;
  updated_at: string | null;
};

export type CreatedAgent = {
  agent_instance_id: string;
  template_code: string;
};

export type AgentPatchFields = {
  title: string;
  intro: string;
  avatar?: string | null;
};

export function agentModeLabel(mode: string | null | undefined): string {
  if ((mode || "single") === "single") {
    return "单智能体模式";
  }
  return "多智能体模式";
}

export function isCustomTemplateCode(templateCode: string | null | undefined): boolean {
  return templateCode === CUSTOM_TEMPLATE_CODE;
}

export function plazaCardTypeClass(templateCode: string | null | undefined): string {
  return isCustomTemplateCode(templateCode) ? "agent-card-custom" : "agent-card-douyin";
}

export function mapPlazaCards(items: Array<Record<string, unknown>> | null | undefined): AgentCard[] {
  return (items || []).map((item) => ({
    agent_instance_id: String(item.agent_instance_id || ""),
    title: String(item.title || ""),
    intro: String(item.intro || ""),
    avatar_url: (item.avatar_url as string | null) || null,
    template_code: String(item.template_code || ""),
    agent_mode: String(item.agent_mode || "single"),
    agent_mode_label: agentModeLabel(item.agent_mode as string | undefined),
    created_at: (item.created_at as string | null) || null,
    updated_at: (item.updated_at as string | null) || null,
  }));
}

export function filterCards(cards: AgentCard[], query: string): AgentCard[] {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return cards;
  }
  return cards.filter(
    (card) =>
      card.title.toLowerCase().includes(needle) ||
      card.intro.toLowerCase().includes(needle),
  );
}

export function createInstancePayload(
  title: string,
  intro = "",
  avatar?: string | null,
  templateCode = DOUYIN_TEMPLATE_CODE,
): Record<string, string> {
  const payload: Record<string, string> = {
    template_code: templateCode,
    title,
    intro: intro || "",
  };
  if (avatar) {
    payload.avatar = avatar;
  }
  return payload;
}

export function patchInstancePayload(
  title: string,
  intro: string,
  avatar?: string | null,
): Record<string, string> {
  const payload: Record<string, string> = {
    title,
    intro,
  };
  if (avatar) {
    payload.avatar = avatar;
  }
  return payload;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString("zh-CN");
}
