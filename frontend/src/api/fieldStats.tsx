import { AmcatFieldStats, AmcatProjectId } from "@/interfaces";
import { amcatFieldStatsSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function useFieldStats(user: AmcatSessionUser, projectId: AmcatProjectId, field: string | undefined) {
  return useQuery({
    queryKey: ["fieldStats", user, projectId, field],
    queryFn: async () => getFieldStats(user, projectId, field || ""),
    enabled: !!field,
  });
}

async function getFieldStats(user: AmcatSessionUser, projectId: AmcatProjectId, field: string) {
  const res = await user.api.get(`index/${projectId}/fields/${field}/stats`);
  const fieldValues: AmcatFieldStats = amcatFieldStatsSchema.parse(res.data);
  return fieldValues;
}
