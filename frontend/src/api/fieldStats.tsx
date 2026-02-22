import { AmcatFieldStats, AmcatIndexId } from "@/interfaces";
import { amcatFieldStatsSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function useFieldStats(user: AmcatSessionUser, indexId: AmcatIndexId, field: string | undefined) {
  return useQuery({
    queryKey: ["fieldStats", user, indexId, field],
    queryFn: async () => getFieldStats(user, indexId, field || ""),
    enabled: !!field,
  });
}

async function getFieldStats(user: AmcatSessionUser, indexId: AmcatIndexId, field: string) {
  const res = await user.api.get(`index/${indexId}/fields/${field}/stats`);
  const fieldValues: AmcatFieldStats = amcatFieldStatsSchema.parse(res.data);
  return fieldValues;
}
