import axios from "axios";
import { axiosClient } from "./axiosClient";
import type { FileClassificationJobResponse } from "@/types/fileClassification";

export async function uploadClassificationFile(
  file: File,
  categorieDefault = ""
): Promise<FileClassificationJobResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("categorie_default", categorieDefault);
  try {
    const { data } = await axiosClient.post<FileClassificationJobResponse>(
      "/classification/upload",
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 0,
      }
    );
    return data;
  } catch (err) {
    if (axios.isAxiosError(err)) {
      const detail =
        (err.response?.data as { detail?: unknown } | undefined)?.detail ?? err.message;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    throw err;
  }
}

export async function getClassificationJobStatus(
  jobId: string,
  limit = 150
): Promise<FileClassificationJobResponse> {
  const { data } = await axiosClient.get<FileClassificationJobResponse>(
    `/classification/upload/${jobId}`,
    { params: { limit } }
  );
  return data;
}
