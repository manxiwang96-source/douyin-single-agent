import { chatHttp, http } from "./http";

export async function getThread(threadId: string): Promise<Record<string, unknown>> {
  const response = await http.get(`/v1/threads/${threadId}`);
  return response.data;
}

export async function postMessage(threadId: string, content: string, clientMessageId: string): Promise<Record<string, unknown>> {
  const response = await chatHttp.post(`/v1/threads/${threadId}/messages`, { content, client_message_id: clientMessageId });
  return response.data;
}

export async function resumeThread(
  threadId: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const response = await chatHttp.post(`/v1/threads/${threadId}/resume`, body);
  return response.data;
}

export async function fetchAuthBlob(url: string): Promise<Blob> {
  const response = await http.get(url, { responseType: "blob" });
  return response.data;
}
