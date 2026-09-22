import { http } from "./http";
import { createInstancePayload } from "../lib/plaza";

export async function listAgentInstances(): Promise<{ items: Array<Record<string, unknown>> }> {
  const response = await http.get("/v1/agent-instances");
  return response.data;
}

export async function createAgentInstance(title: string, intro: string, avatar?: string | null) {
  const response = await http.post("/v1/agent-instances", createInstancePayload(title, intro, avatar));
  return response.data;
}

export async function openAgentInstance(agentInstanceId: string): Promise<{
  agent_instance_id: string;
  thread_id: string;
  updated_at: string;
}> {
  const response = await http.post(`/v1/agent-instances/${agentInstanceId}/open`);
  return response.data;
}

export async function getAgentSidebar(agentInstanceId: string): Promise<Record<string, unknown>> {
  const response = await http.get(`/v1/agent-instances/${agentInstanceId}/sidebar`);
  return response.data;
}
