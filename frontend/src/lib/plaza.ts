export const DOUYIN_TEMPLATE_CODE = "douyin_ops";

export const DOUYIN_TEMPLATE = {
  template_code: DOUYIN_TEMPLATE_CODE,
  title: "抖音运营助手",
  description: "围绕抖音账号和话题做运营规划，并通过已绑定工作流做线索发现与真实触达",
};

export type AgentCard = {
  agent_instance_id: string;
  title: string;
  intro: string;
  avatar_url: string | null;
  agent_mode: string;
  agent_mode_label: string;
  created_at: string | null;
  updated_at: string | null;
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

export function mapPlazaCards(items: Array<Record<string, unknown>> | null | undefined): AgentCard[] {
  return (items || []).map((item) => ({
    agent_instance_id: String(item.agent_instance_id || ""),
    title: String(item.title || ""),
    intro: String(item.intro || ""),
    avatar_url: (item.avatar_url as string | null) || null,
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
): Record<string, string> {
  const payload: Record<string, string> = {
    template_code: DOUYIN_TEMPLATE_CODE,
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
