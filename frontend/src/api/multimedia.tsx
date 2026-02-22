import { AmcatIndexId, MultimediaListItem, MultimediaPresignedPost } from "@/interfaces";
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
  indexId?: AmcatIndexId | undefined,
  params?: MultimediaParams,
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ["multimediaList", user, indexId, params],
    queryFn: () => getMultimediaList(user, indexId, params),
    enabled: user != null && indexId != null && enabled,
  });
}

export function useMultimediaConcatenatedList(
  user?: AmcatSessionUser,
  indexId?: AmcatIndexId | undefined,
  prefixes?: string[],
) {
  // special case of useMultimediaList.
  // get all items with one of the specified prefixes

  const results = useQueries({
    queries: (prefixes || []).map((prefix) => ({
      queryKey: ["multimediaList", user, indexId, { prefix }],
      queryFn: () => getMultimediaList(user, indexId, { prefix }),
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
  indexId?: AmcatIndexId,
  params?: MultimediaParams,
): Promise<MultimediaListItem[]> {
  if (!user || !indexId) throw new Error("Missing user or indexId");

  const batchsize = 100000;
  let data: MultimediaListItem[] = [];
  let start_after: string | undefined = params?.start_after;

  while (true) {
    const p: MultimediaParams = { ...(params || {}), n: params?.n || batchsize };
    if (start_after) p.start_after = start_after;
    const res = await user.api.get(`/index/${indexId}/multimedia/list`, { params });
    const batch = z.array(amcatMultimediaListItem).parse(res.data);
    data = [...data, ...batch];
    if (batch.length < batchsize) break;
    start_after = batch[batch.length - 1].key;
  }
  return data;
}

export function useMultimediaPresignedPost(
  user?: AmcatSessionUser,
  indexId?: AmcatIndexId | undefined,
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ["multimediaPresignedPost", user, indexId],
    queryFn: async () => {
      if (!user || !indexId) return undefined;
      const res = await user?.api.get(`index/${indexId}/multimedia/presigned_post`);
      return amcatMultimediaPresignedPost.parse(res.data);
    },
    enabled: enabled && user != null && indexId != null,
  });
}

export function useMultimediaPresignedGet(user?: AmcatSessionUser, indexId?: AmcatIndexId | undefined, key?: string) {
  return useQuery({
    queryKey: ["presignedUrl", user, indexId, key],
    queryFn: async () => {
      if (!user || !indexId || !key) return undefined;
      const res = await user.api.get(`/index/${indexId}/multimedia/presigned_get`, { params: { key } });
      return amcatMultimediaPresignedGet.parse(res.data);
    },
    enabled: user != null && indexId != null && key != null,
    retry: false, // because
  });
}

export function useMutateMultimedia(
  user?: AmcatSessionUser,
  indexId?: AmcatIndexId | undefined,
  presignedPost?: MultimediaPresignedPost,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: FileWithPath) => {
      if (!user || !indexId || !presignedPost) throw new Error("Missing user, indexId or presignedPost");
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
      queryClient.invalidateQueries({ queryKey: ["multimediaList", user || "", indexId || ""] });
      queryClient.invalidateQueries({ queryKey: ["multimediaFullList", user || "", indexId || ""] });
      toast.success("File uploaded");
    },
  });
}
