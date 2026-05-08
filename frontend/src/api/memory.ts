import { axiosClient } from "@/api/axiosClient";

export interface LongTermMemoryItem {
  id: number;
  namespace: string;
  memory_key: string;
  memory_value: string;
  score: number;
  metadata: Record<string, unknown>;
  updated_at: string;
}

export interface ShortTermMemoryItem {
  id: number;
  session_id: string;
  turn_index: number;
  role: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function getLongTermMemory(
  namespace: string,
  limit = 20
): Promise<LongTermMemoryItem[]> {
  const { data } = await axiosClient.get<{ items: LongTermMemoryItem[] }>("/memory/long-term", {
    params: { namespace, limit },
  });
  return data.items || [];
}

export async function getShortTermMemory(
  sessionId: string,
  limit = 20
): Promise<ShortTermMemoryItem[]> {
  const { data } = await axiosClient.get<{ items: ShortTermMemoryItem[] }>("/memory/short-term", {
    params: { session_id: sessionId, limit },
  });
  return data.items || [];
}

