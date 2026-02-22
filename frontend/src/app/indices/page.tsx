"use client";

import { useAmcatConfig } from "@/api/config";
import { SelectIndex } from "@/components/Index/SelectIndex";
import { Loading } from "@/components/ui/loading";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { useRouter } from "next/navigation";

export default function Index() {
  const { user } = useAmcatSession();
  const { data: serverConfig, isLoading } = useAmcatConfig();
  if (isLoading) return <Loading />;
  if (!serverConfig) return <div className="p-3">Could not load server configuration</div>;

  return (
    <div className="h-full w-full max-w-7xl animate-fade-in px-0 dark:prose-invert md:px-4">
      <div className="mt-[4vh]">
        <SelectIndex />
      </div>
    </div>
  );
}
