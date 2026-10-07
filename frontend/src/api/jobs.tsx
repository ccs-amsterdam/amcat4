import { AmcatJob } from "@/interfaces";
import { amcatJobSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function jobIsActive(job?: AmcatJob | null) {
  return job?.status === "pending" || job?.status === "running";
}

export function useJob(user?: AmcatSessionUser, jobId?: string | null) {
  return useQuery({
    queryKey: ["job", user, jobId],
    queryFn: async () => {
      const res = await user!.api.get(`jobs/${jobId}`);
      return amcatJobSchema.parse(res.data);
    },
    enabled: user != null && jobId != null,
    // poll while the job is pending or running
    refetchInterval: (query) => (jobIsActive(query.state.data) ? 2000 : false),
  });
}

export function useCancelJob(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string) => {
      if (!user) throw new Error("Not logged in");
      return await user.api.delete(`jobs/${jobId}`);
    },
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ["job", user, jobId] });
    },
  });
}
