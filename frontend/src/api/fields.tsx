import { AmcatField, AmcatProjectId, UpdateAmcatField } from "@/interfaces";
import { amcatFieldSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { toast } from "sonner";
import { z } from "zod";

// TODO: make function, use types
const DEFAULT_CLIENT_SETTINGS: Record<string, any> = {
  date: {
    inDocument: true,
    inList: true,
    inListSummary: true,
  },
  text: {
    inDocument: true,
    inList: true,
  },
  title: {
    inDocument: true,
    inList: true,
    isHeading: true,
  },
  url: {
    inDocument: true,
  },
  __DEFAULT__: {
    inDocument: true,
    inList: true,
  },
};

export function useFields(user?: AmcatSessionUser, projectId?: AmcatProjectId | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ["fields", user, projectId],
    queryFn: () => getFields(user, projectId || ""),
    enabled: enabled && user != null && projectId != null,
  });
}

async function getFields(user?: AmcatSessionUser, projectId?: AmcatProjectId) {
  if (!user || !projectId) return undefined;
  const res = await user.api.get(`/index/${projectId}/fields`);
  const fieldsArray = Object.keys(res.data).map((name) => ({ name, ...res.data[name] }));
  const fields = z.array(amcatFieldSchema).parse(fieldsArray);
  return fields.map((f) => {
    // set default values
    const default_settings = DEFAULT_CLIENT_SETTINGS[f.name] || DEFAULT_CLIENT_SETTINGS["__DEFAULT__"];
    f.client_settings = { ...default_settings, ...f.client_settings };
    return f;
  });
}

export function getField(fields: AmcatField[] | undefined, fieldname: string): AmcatField | undefined {
  return fields?.find((f) => f.name === fieldname);
}

interface MutateFieldsParams {
  fields: UpdateAmcatField[];
  action: "create" | "delete" | "update";
}

export function useMutateFields(user?: AmcatSessionUser, projectId?: AmcatProjectId | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fields, action }: MutateFieldsParams) => {
      if (!user) throw new Error("Not logged in");
      return mutateFields(user, projectId || "", action, fields);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["fields", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["articles", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["article", user, projectId] });

      const fieldnames = variables.fields.map((f) => f.name).join(", ");
      if (variables.action === "create") toast.success(`Created fields: ${fieldnames}`);
      if (variables.action === "update") toast.success(`Updated fields: ${fieldnames}`);
      if (variables.action === "delete") toast.success(`Deleted fields: ${fieldnames}`);
    },
  });
}

async function mutateFields(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  action: "create" | "delete" | "update",
  fields: UpdateAmcatField[],
) {
  if (!projectId) return undefined;
  const fieldsObject: Record<string, any> = {};

  fields.forEach((f) => {
    if (!f.name) return;
    fieldsObject[f.name] = {};
    if (f.type) fieldsObject[f.name].type = f.type;
    if (f.elastic_type) {
      if (action !== "create") throw new Error("Cannot change elastic_type of existing field");
      fieldsObject[f.name].type = f.elastic_type;
    }
    if (f.identifier) {
      if (action !== "create") throw new Error("Cannot change identifier of existing field");
      fieldsObject[f.name].identifier = f.identifier;
    }

    if (f.metareader) fieldsObject[f.name].metareader = f.metareader;
    if (f.client_settings) fieldsObject[f.name].client_settings = f.client_settings;
  });

  if (action === "delete") {
    return await user.api.delete(`/index/${projectId}/fields`, { data: fields.map((f) => f.name) });
  } else if (action === "create") {
    return await user.api.post(`/index/${projectId}/fields`, fieldsObject);
  } else if (action === "update") {
    return await user.api.put(`/index/${projectId}/fields`, fieldsObject);
  }
}
