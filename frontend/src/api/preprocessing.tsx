import {
  amcatPreprocessingInstruction,
  amcatPreprocessingInstructionDetails,
  amcatPreprocessingInstructionStatus,
  amcatPreprocessingTask,
} from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { toast } from "sonner";
import { z } from "zod";

export function usePreprocessingTasks(user: AmcatSessionUser) {
  return useQuery({
    queryKey: ["preprocessingTasks"],
    queryFn: async () => {
      const res = await user.api.get("/preprocessing_tasks");
      return z.array(amcatPreprocessingTask).parse(res.data);
    },
  });
}

export function usePreprocessingInstructions(user: AmcatSessionUser, projectId: string) {
  return useQuery({
    queryKey: ["preprocessingInstructions", user, projectId],
    queryFn: async () => {
      const res = await user.api.get(`/index/${projectId}/preprocessing`);
      return z.array(amcatPreprocessingInstruction).parse(res.data);
    },
  });
}

export function useMutatePreprocessingInstruction(user: AmcatSessionUser, projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (instruction: any) => {
      await user.api.post(`/index/${projectId}/preprocessing`, instruction);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["preprocessingInstructions", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["fields", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["articles", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["aggregate", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["article", user, projectId] });
      toast.success("Preprocessing instruction submitted");
    },
  });
}

export function usePreprocessingInstructionDetails(
  user: AmcatSessionUser,
  projectId: string,
  field: string,
  extra_options = {},
) {
  return useQuery({
    queryKey: ["preprocessingInstructionDetails", user, projectId, field],
    queryFn: async () => {
      const res = await user.api.get(`/index/${projectId}/preprocessing/${field}`);
      return amcatPreprocessingInstructionDetails.parse(res.data);
    },
    staleTime: 1000,
    ...extra_options,
  });
}

export function usePreprocessingInstructionStatus(
  user: AmcatSessionUser,
  projectId: string,
  field: string,
  extra_options = {},
) {
  return useQuery({
    queryKey: ["preprocessingInstructionStatus", user, projectId, field],
    queryFn: async () => {
      const res = await user.api.get(`/index/${projectId}/preprocessing/${field}/status`);
      return amcatPreprocessingInstructionStatus.parse(res.data);
    },
    staleTime: 1000,
    ...extra_options,
  });
}

export function useMutatePreprocessingInstructionAction(user: AmcatSessionUser, projectId: string, field: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (action: any) => {
      await user.api.post(`/index/${projectId}/preprocessing/${field}/status`, { action });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["preprocessingInstructionDetails", user, projectId, field] });
      queryClient.invalidateQueries({ queryKey: ["preprocessingInstructionStatus", user, projectId, field] });
      toast.success(`Sent preprocessing action ${variables} to ${field}`);
    },
  });
}
