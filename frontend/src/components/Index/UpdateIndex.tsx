"use client";

import { useMutateIndex } from "@/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel } from "@/components/ui/form";
import { AmcatIndex } from "@/interfaces";
import { amcatIndexUpdateSchema, contactInfoSchema } from "@/schemas";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { JSONForm } from "../ui/jsonForm";

export function UpdateIndex({ index, children }: { index: AmcatIndex; children?: React.ReactNode }) {
  const { user } = useAmcatSession();
  const { mutateAsync } = useMutateIndex(user);
  const [open, setOpen] = useState(false);
  const form = useForm<z.input<typeof amcatIndexUpdateSchema>>({
    resolver: zodResolver(amcatIndexUpdateSchema),
    defaultValues: { ...index, archive: undefined },
  });
  if (!index) return null;

  function onSubmit(values: z.input<typeof amcatIndexUpdateSchema>) {
    mutateAsync(amcatIndexUpdateSchema.parse(values)).then(() => setOpen(false));
  }

  return (
    <Dialog open={open} onOpenChange={(open) => setOpen(open)}>
      <DialogTrigger asChild className="text-lg">
        {children}
      </DialogTrigger>
      <DialogContent aria-describedby={undefined} className="w-[500px] max-w-[90vw]">
        <DialogHeader>
          <DialogTitle>Edit Index</DialogTitle>
          <DialogDescription>{index.id}</DialogDescription>
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
                      <FormLabel>Index Name</FormLabel>
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
                        placeholder="A short description of what this index is about"
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
              Update Index Settings
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
