import { axiosClient } from "./axiosClient";
import type { ProductionDashboardResponse } from "@/types/dashboard";

export async function getProductionDashboard(
  params: { start_year?: number; max_articles?: number; article?: string } = {}
): Promise<ProductionDashboardResponse> {
  const { data } = await axiosClient.get<ProductionDashboardResponse>("/dashboard/production_trends", {
    params,
  });
  return data;
}
