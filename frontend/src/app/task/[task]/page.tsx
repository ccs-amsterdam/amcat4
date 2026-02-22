"use client";
import { use } from "react";

import { useTaskStatus } from "@/api/task";
import { Loading } from "@/components/ui/loading";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
interface Props {
  params: Promise<{ task: string }>;
}
export default function Task(props: Props) {
  const params = use(props.params);
  //TODO: Make progress report nicer, maybe add progress bar?
  const taskId = decodeURI(params.task);
  const { user } = useAmcatSession();
  const { data } = useTaskStatus(user, taskId);
  if (user == null || data == null) return <Loading />;
  if (taskId == null) return <div className="bg-warn">Please provide taskId in URL</div>;
  return (
    <div className="flex h-full w-full flex-auto flex-col pt-6 md:pt-6">
      <div className="flex justify-center">
        <div className="flex w-full max-w-[1000px] flex-col px-5 py-5 sm:px-10">
          <h1>Task status: {data["completed"] ? "Done" : "In progress"}</h1>
          <p>Task description: {data["task"]["description"]}</p>
          <pre className="mt-2 border p-1 text-xs">
            Raw task output:{"\n\n"}
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
