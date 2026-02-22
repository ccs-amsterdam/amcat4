

import { useAmcatBranding, useMutateBranding } from "@/api/branding";
import { useAmcatConfig } from "@/api/config";
import { useCurrentUserDetails } from "@/api/userDetails";
import { Loading } from "@/components/ui/loading";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { amcatBrandingSchema, informationLinksSchema, linkArraySchema } from "@/schemas";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { JSONForm } from "@/components/ui/jsonForm";

export function ServerBrandingForm() {
  const { user } = useAmcatSession();
  const { data: userDetails, isLoading: loadingUserDetails } = useCurrentUserDetails(user);
  const mutateBranding = useMutateBranding(user);
  const { data: branding, isLoading: loadingBranding } = useAmcatBranding();
  const { data: config } = useAmcatConfig();

  const brandingForm = useForm<z.input<typeof amcatBrandingSchema>, unknown, z.output<typeof amcatBrandingSchema>>({
    resolver: zodResolver(amcatBrandingSchema),
    defaultValues: {
      ...branding,
    },
  });

  function brandingFormSubmit(values: z.output<typeof amcatBrandingSchema>) {
    mutateBranding.mutateAsync(values).catch(console.error);
  }

  if (loadingBranding || loadingUserDetails) return <Loading />;
  const isAdmin = userDetails?.role === "ADMIN" || config?.authorization === "no_auth";

  return (
    <Form {...brandingForm}>
      <form onSubmit={brandingForm.handleSubmit(brandingFormSubmit)} className="space-y-6">
        <FormField
          control={brandingForm.control}
          name="server_name"
          disabled={!isAdmin}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Server Name</FormLabel>
              <FormControl>
                <Input {...field} value={field.value ?? ""} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        ></FormField>
        <FormField
          control={brandingForm.control}
          name="server_url"
          disabled={!isAdmin}
          render={({ field }) => (
            <FormItem>
              <FormLabel>External Project URL</FormLabel>
              <FormControl>
                <Input {...field} value={field.value ?? ""} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        ></FormField>
        <FormField
          control={brandingForm.control}
          name="server_icon"
          disabled={!isAdmin}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Server Icon URL</FormLabel>
              <FormControl>
                <Input {...field} value={field.value ?? ""} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        ></FormField>
        <FormField
          control={brandingForm.control}
          name="welcome_text"
          disabled={!isAdmin}
          render={({ field }) => (
            <FormItem>
              <FormLabel>Welcome Text (Markdown)</FormLabel>
              <FormControl>
                <Textarea
                  rows={6}
                  placeholder="# Title and text using **MarkDown**"
                  {...field}
                  value={field.value ?? ""}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        ></FormField>
        <JSONForm
          control={brandingForm.control}
          name="client_data.welcome_buttons"
          label="Action Buttons below Welcome Text"
          schema={linkArraySchema}
        />
        <JSONForm
          control={brandingForm.control}
          name="client_data.information_links"
          label="Links column in homepage footer"
          schema={informationLinksSchema}
        />
        {!isAdmin ? null : <Button type="submit">Save changes</Button>}
      </form>
    </Form>
  );
}
