import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { AmcatBranding } from "@/interfaces";
import { amcatBrandingSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { toast } from "sonner";
import { z } from "zod";

export function useAmcatBranding() {
  return useQuery({
    queryKey: ["branding"],
    queryFn: () => getAmcatBranding(),
    staleTime: 1000 * 60 * 60 * 1,
  });
}

async function getAmcatBranding() {
  function safeParseJson(input: string | null | undefined) {
    try {
      return input == null ? null : JSON.parse(input);
    } catch (error) {
      toast("JSON error parsing branding data, see console for more details");
      console.error(error);
    }
  }

  const res: any = await axios.get(`/api/config/branding`, { timeout: 3000 });
  const result = amcatBrandingSchema.safeParse(res.data);
  if (result.success) return result.data;
  toast("Error parsing branding data, see console for more details");
}

export function useMutateBranding(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (value: z.input<typeof amcatBrandingSchema>) => {
      // AmCAT API expects a single json blob for the client data
      if (!user) throw new Error("Not logged in");
      return mutateBranding(user, value);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["branding"] });
    },
  });
}

async function mutateBranding(user: AmcatSessionUser, value: AmcatBranding) {
  return await user.api.put(`config/branding`, value);
}
