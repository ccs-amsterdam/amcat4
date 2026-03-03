import { AmcatConfig } from "@/interfaces";
import { amcatConfigSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

export function useAmcatConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: () => getAmcatConfig(),
    staleTime: 1000 * 60 * 60 * 1,
  });
}

async function getAmcatConfig() {
  const res = await axios.get(`/api/config`, { timeout: 3000 });
  const config: AmcatConfig = amcatConfigSchema.parse(res.data);
  return config;
}
