import { axiosClient } from "./axiosClient";
import type { AskAgentPayload, AskAgentResponse } from "@/types/askAgent";

export async function postAskAgent(
  payload: AskAgentPayload
): Promise<AskAgentResponse> {
  const { data } = await axiosClient.post<AskAgentResponse>("/ask_agent", payload);
  try {
    localStorage.setItem(
      "sotipapier_last_ask_agent",
      JSON.stringify({
        at: new Date().toISOString(),
        payload,
        response: data,
      })
    );
    window.dispatchEvent(new Event("sotipapier:ask-agent-updated"));
  } catch {
    // Ignore localStorage errors (private mode / quota).
  }
  return data;
}
