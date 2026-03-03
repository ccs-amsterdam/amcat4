import { AmcatProjectId, MultimediaListItem, MultimediaPresignedPost } from "@/interfaces";
import { amcatMultimediaListItem, amcatMultimediaPresignedGet, amcatMultimediaPresignedPost } from "@/schemas";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useMemo } from "react";
import { FileWithPath } from "react-dropzone";
import { toast } from "sonner";
import { z } from "zod";

interface MultimediaParams {
  prefix?: string | string[];
  start_after?: string;
  n?: number;
  presigned_get?: boolean;
  metadata?: boolean;
  recursive?: boolean;
}

export function useMultimediaList(
  user?: AmcatSessionUser,
  projectId?: AmcatProjectId | undefined,
  params?: MultimediaParams,
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ["multimediaList", user, projectId, params],
    queryFn: () => getMultimediaList(user, projectId, params),
    enabled: user != null && projectId != null && enabled,
  });
}

export function useMultimediaConcatenatedList(
  user?: AmcatSessionUser,
  projectId?: AmcatProjectId | undefined,
  prefixes?: string[],
) {
  // special case of useMultimediaList.
  // get all items with one of the specified prefixes

  const results = useQueries({
    queries: (prefixes || []).map((prefix) => ({
      queryKey: ["multimediaList", user, projectId, { prefix }],
      queryFn: () => getMultimediaList(user, projectId, { prefix }),
    })),
  });

  // flatten the results
  return useMemo(() => {
    if (!prefixes || prefixes.length === 0) return undefined;
    return results.flatMap((r) => r.data || []);
  }, [prefixes, results]);
}

async function getMultimediaList(
  user?: AmcatSessionUser,
  projectId?: AmcatProjectId,
  params?: MultimediaParams,
): Promise<MultimediaListItem[]> {
  if (!user || !projectId) throw new Error("Missing user or projectId");

  const batchsize = 100000;
  let data: MultimediaListItem[] = [];
  let start_after: string | undefined = params?.start_after;

  while (true) {
    const p: MultimediaParams = { ...(params || {}), n: params?.n || batchsize };
    if (start_after) p.start_after = start_after;
    const res = await user.api.get(`/index/${projectId}/multimedia/list`, { params });
    const batch = z.array(amcatMultimediaListItem).parse(res.data);
    data = [...data, ...batch];
    if (batch.length < batchsize) break;
    start_after = batch[batch.length - 1].key;
  }
  return data;
}

export function useMultimediaPresignedPost(
  user?: AmcatSessionUser,
  projectId?: AmcatProjectId | undefined,
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ["multimediaPresignedPost", user, projectId],
    queryFn: async () => {
      if (!user || !projectId) return undefined;
      const res = await user?.api.get(`index/${projectId}/multimedia/presigned_post`);
      return amcatMultimediaPresignedPost.parse(res.data);
    },
    enabled: enabled && user != null && projectId != null,
  });
}

export function useMultimediaPresignedGet(user?: AmcatSessionUser, projectId?: AmcatProjectId | undefined, key?: string) {
  return useQuery({
    queryKey: ["presignedUrl", user, projectId, key],
    queryFn: async () => {
      if (!user || !projectId || !key) return undefined;
      const res = await user.api.get(`/index/${projectId}/multimedia/presigned_get`, { params: { key } });
      return amcatMultimediaPresignedGet.parse(res.data);
    },
    enabled: user != null && projectId != null && key != null,
    retry: false, // because
  });
}

export function useMutateMultimedia(
  user?: AmcatSessionUser,
  projectId?: AmcatProjectId | undefined,
  presignedPost?: MultimediaPresignedPost,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: FileWithPath) => {
      if (!user || !projectId || !presignedPost) throw new Error("Missing user, projectId or presignedPost");
      const body = new FormData();
      body.append("key", file.path || file.name);
      for (const [key, value] of Object.entries(presignedPost.form_data)) body.append(key, value);
      body.append("file", file);

      const res = await fetch(presignedPost.url, {
        method: "POST",
        body,
      });
      if (!res.ok) throw new Error(`Failed to upload file: ${res.statusText}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["multimediaList", user || "", projectId || ""] });
      queryClient.invalidateQueries({ queryKey: ["multimediaFullList", user || "", projectId || ""] });
      toast.success("File uploaded");
    },
  });
}
