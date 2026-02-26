import { useCurrentUserDetails } from "@/api/userDetails";
import { Loading } from "@/components/ui/loading";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { amcatApiKeySchema, amcatUserRoles } from "@/schemas";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useMutateApiKeys } from "@/api/api_keys";
import { useAmcatProjectRoles } from "@/api/projects";
import { AmcatApiKey, AmcatProjectId, AmcatUserRole } from "@/interfaces";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "../ui/select";
import { roleHigherThan } from "@/api/util";
import { Button } from "../ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { X } from "lucide-react";
import { useState } from "react";
import set from "date-fns/esm/fp/set/index.js";

const now = new Date();
const nextYear = now.setFullYear(now.getFullYear() + 1);

const newDefault = {
  id: "new",
  name: "",
  expires_at: new Date(nextYear),
  restrictions: {
    edit_api_keys: false,
    server_role: undefined,
    default_project_role: undefined,
    project_roles: {},
  },
};

export function CreateApiKey({
  current,
  onClose,
  setShowKey,
}: {
  current: AmcatApiKey | "new";
  onClose: () => void;
  setShowKey: (key: string) => void;
}) {
  const { user } = useAmcatSession();
  const { data: userDetails, isLoading: loadingUserDetails } = useCurrentUserDetails(user);
  const { data: userProjectRoles, isLoading: loadingUserProjects } = useAmcatProjectRoles(user);
  const mutateApiKeys = useMutateApiKeys(user);

  const apikeyForm = useForm<z.input<typeof amcatApiKeySchema>, unknown, z.output<typeof amcatApiKeySchema>>({
    resolver: zodResolver(amcatApiKeySchema),
    defaultValues: current == "new" ? newDefault : current,
  });

  function apikeyFormSubmit(values: z.output<typeof amcatApiKeySchema>) {
    mutateApiKeys
      .mutateAsync({
        update: values,
        action: current === "new" ? "create" : "update",
      })
      .then((apikey) => {
        if (apikey) {
          setShowKey(apikey);
        } else {
          onClose();
        }
      });
  }

  if (loadingUserDetails || loadingUserProjects) return <Loading />;

  return (
    <Form {...apikeyForm}>
      <form onSubmit={apikeyForm.handleSubmit(apikeyFormSubmit)} className="space-y-6">
        <div className="grid grid-cols-2 gap-3">
          <FormField
            control={apikeyForm.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>API Key Name*</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value ?? ""} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          ></FormField>
          <FormField
            control={apikeyForm.control}
            name="expires_at"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Expiration date*</FormLabel>
                <FormControl>
                  <DateInput value={field.value} onChange={field.onChange} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          ></FormField>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <FormField
            control={apikeyForm.control}
            name="restrictions.server_role"
            render={({ field }) => (
              <FormItem>
                <FormLabel>restrict server role</FormLabel>
                <FormControl>
                  <RoleInput value={field.value || undefined} onChange={field.onChange} actual={userDetails?.role} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          ></FormField>
          <FormField
            control={apikeyForm.control}
            name="restrictions.default_project_role"
            render={({ field }) => (
              <FormItem>
                <FormLabel>restrict project role</FormLabel>
                <FormControl>
                  <RoleInput value={field.value || undefined} onChange={field.onChange} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          ></FormField>
        </div>
      </form>
      <div className="mt-6">
        <FormField
          control={apikeyForm.control}
          name="restrictions.project_roles"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Custom project role restrictions (overrides restrict project role)</FormLabel>
              <FormControl>
                <ProjectRoles value={field.value || {}} onChange={field.onChange} actual={userProjectRoles || {}} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        ></FormField>
      </div>
      <div className="mt-6 flex items-center justify-end gap-2">
        <Button type="submit" onClick={apikeyForm.handleSubmit(apikeyFormSubmit)}>
          {current === "new" ? "Create API Key" : "Update API Key"}
        </Button>
        <Button variant="outline" className="" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </Form>
  );
}

function ProjectRoles({
  value,
  onChange,
  actual,
}: {
  value: Record<string, AmcatUserRole>;
  onChange: (value: Record<string, AmcatUserRole>) => void;
  actual: Record<AmcatProjectId, AmcatUserRole>;
}) {
  const unassigned = Object.entries(actual).filter(([projectId]) => !(projectId in value));

  return (
    <div>
      {Object.entries(value).map(([projectId, role]) => (
        <div key={projectId} className="my-1 grid grid-cols-[1fr,150px,min-content] items-center gap-3 rounded  py-1">
          <div className="h-full rounded bg-primary/10 p-2">{projectId}</div>
          <div>
            <RoleInput
              value={role || undefined}
              onChange={(newRole) => {
                const newValue = { ...value, [projectId]: newRole };
                onChange(newValue);
              }}
              actual={actual ? actual[projectId] : undefined}
            />
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              const newValue = { ...value };
              delete newValue[projectId];
              onChange(newValue);
            }}
          >
            <X />
          </Button>
        </div>
      ))}
      <DropdownMenu>
        <DropdownMenuTrigger className={unassigned.length > 0 ? "" : "hidden"} asChild>
          <Button>Add project role</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {unassigned.map(([projectId, role]) => {
            return (
              <DropdownMenuItem
                key={projectId}
                onClick={() => {
                  const newValue = { ...value, [projectId]: role };
                  onChange(newValue);
                }}
              >
                <div className="min-w-16">{projectId}</div>
                <span className="text-foreground/60">{role}</span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function DateInput({ value, onChange }: { value: Date; onChange: (date: Date) => void }) {
  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const date = new Date(e.target.value);
    if (!isNaN(date.getTime())) {
      onChange(date);
    }
  }

  return (
    <Input type="datetime-local" value={value.toISOString().substring(0, 16)} onChange={handleChange} className="" />
  );
}

function RoleInput({
  value,
  onChange,
  actual,
}: {
  value?: AmcatUserRole;
  onChange: (roles: AmcatUserRole) => void;
  actual?: AmcatUserRole;
}) {
  return (
    <div className="flex items-center gap-1">
      <Select onValueChange={(val) => onChange(val as AmcatUserRole)} value={value}>
        <SelectTrigger className="border-none bg-primary/10 ">
          <SelectValue placeholder="Select role" />
        </SelectTrigger>
        <SelectContent className="bg-background">
          <SelectGroup>
            {amcatUserRoles.map((role) => {
              const higher = actual ? roleHigherThan(role, actual) : false;
              return (
                <SelectItem key={role} value={role} className={higher ? "opacity-50" : ""}>
                  {role}
                </SelectItem>
              );
            })}
          </SelectGroup>
        </SelectContent>
      </Select>
      {/*Doesn't work because apparently cannot set a form value to undefined*/}
      {/*<Button type="button" variant="ghost" size="icon" onClick={() => onChange(undefined)}>
        <X />
      </Button>*/}
    </div>
  );
}
