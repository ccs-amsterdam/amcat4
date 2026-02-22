import { AmcatField, AmcatIndexId, UpdateAmcatField } from "@/interfaces";
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

export function useFields(user?: AmcatSessionUser, indexId?: AmcatIndexId | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ["fields", user, indexId],
    queryFn: () => getFields(user, indexId || ""),
    enabled: enabled && user != null && indexId != null,
  });
}

async function getFields(user?: AmcatSessionUser, indexId?: AmcatIndexId) {
  if (!user || !indexId) return undefined;
  const res = await user.api.get(`/index/${indexId}/fields`);
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

export function useMutateFields(user?: AmcatSessionUser, indexId?: AmcatIndexId | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fields, action }: MutateFieldsParams) => {
      if (!user) throw new Error("Not logged in");
      return mutateFields(user, indexId || "", action, fields);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["fields", user, indexId] });
      queryClient.invalidateQueries({ queryKey: ["articles", user, indexId] });
      queryClient.invalidateQueries({ queryKey: ["article", user, indexId] });

      const fieldnames = variables.fields.map((f) => f.name).join(", ");
      if (variables.action === "create") toast.success(`Created fields: ${fieldnames}`);
      if (variables.action === "update") toast.success(`Updated fields: ${fieldnames}`);
      if (variables.action === "delete") toast.success(`Deleted fields: ${fieldnames}`);
    },
  });
}

async function mutateFields(
  user: AmcatSessionUser,
  indexId: AmcatIndexId,
  action: "create" | "delete" | "update",
  fields: UpdateAmcatField[],
) {
  if (!indexId) return undefined;
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
    return await user.api.delete(`/index/${indexId}/fields`, { data: fields.map((f) => f.name) });
  } else if (action === "create") {
    return await user.api.post(`/index/${indexId}/fields`, fieldsObject);
  } else if (action === "update") {
    return await user.api.put(`/index/${indexId}/fields`, fieldsObject);
  }
}
