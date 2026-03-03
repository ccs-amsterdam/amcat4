import { AmcatFieldValues, AmcatProjectId } from "@/interfaces";
import { amcatFieldValuesSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function useFieldValues(user: AmcatSessionUser, projectId: AmcatProjectId, field: string | undefined) {
  return useQuery({
    queryKey: ["fieldValues", user, projectId, field],
    queryFn: async () => getFieldValues(user, projectId, field || ""),
    enabled: !!field,
  });
}

async function getFieldValues(user: AmcatSessionUser, projectId: AmcatProjectId, field: string) {
  const res = await user.api.get(`index/${projectId}/fields/${field}/values`);
  const fieldValues: AmcatFieldValues = amcatFieldValuesSchema.parse(res.data);
  return fieldValues;
}
