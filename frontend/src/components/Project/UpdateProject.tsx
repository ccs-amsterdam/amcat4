import { useMutateProject } from "@/api/project";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel } from "@/components/ui/form";
import { AmcatProject } from "@/interfaces";
import { amcatProjectUpdateSchema, contactInfoSchema } from "@/schemas";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { JSONForm } from "../ui/jsonForm";

export function UpdateProject({ project, children }: { project: AmcatProject; children?: React.ReactNode }) {
  const { user } = useAmcatSession();
  const { mutateAsync } = useMutateProject(user);
  const [open, setOpen] = useState(false);
  const form = useForm<z.input<typeof amcatProjectUpdateSchema>>({
    resolver: zodResolver(amcatProjectUpdateSchema),
    defaultValues: { ...project, archive: undefined },
  });
  if (!project) return null;

  function onSubmit(values: z.input<typeof amcatProjectUpdateSchema>) {
    mutateAsync(amcatProjectUpdateSchema.parse(values)).then(() => setOpen(false));
  }

  return (
    <Dialog open={open} onOpenChange={(open) => setOpen(open)}>
      <DialogTrigger asChild className="text-lg">
        {children}
      </DialogTrigger>
      <DialogContent aria-describedby={undefined} className="w-[500px] max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>Edit Project</DialogTitle>
          <DialogDescription>{project.id}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-3">
            <div className="space-y-4">
              <div className="flex gap-3">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Project Name</FormLabel>
                      <FormControl>
                        <Input {...field} value={field.value ?? ""} />
                      </FormControl>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="folder"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Folder</FormLabel>
                      <FormControl>
                        <Input placeholder="filepath/for/organizing" {...field} value={field.value ?? ""} />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="A short description of what this project is about"
                        {...field}
                        value={field.value ?? ""}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              <JSONForm control={form.control} name="contact" label="Contact information" schema={contactInfoSchema} />

              <FormField
                control={form.control}
                name="image_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Image URL</FormLabel>
                    <FormControl>
                      <Input placeholder="Optional image URL for good vibes" {...field} value={field.value ?? ""} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
            <Button className="mt-3" type="submit">
              Update Project Settings
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
