import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/jobs/$job")({
  component: JobPage,
});

import { useJob } from "@/api/jobs";
import { Loading } from "@/components/ui/loading";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import JobStatus from "@/components/Update/JobStatus";

function JobPage() {
  const { job: jobParam } = Route.useParams();
  const jobId = decodeURI(jobParam);
  const { user } = useAmcatSession();
  const { data: job } = useJob(user, jobId);
  if (user == null || job == null) return <Loading />;

  const destination = job.params?.destination as string | undefined;
  const source = job.params?.source as string | undefined;

  return (
    <div className="flex h-full w-full flex-auto flex-col pt-6 md:pt-6">
      <div className="flex justify-center">
        <div className="flex w-full max-w-[1000px] flex-col gap-4 px-5 py-5 sm:px-10">
          <h1 className="text-2xl font-semibold">{job.type === "copy" ? "Copy documents" : `Job: ${job.type}`}</h1>
          {job.type === "copy" && source && destination && (
            <p className="text-sm">
              From{" "}
              <Link className="text-primary hover:underline" to="/projects/$project/dashboard" params={{ project: source }}>
                {source}
              </Link>{" "}
              to{" "}
              <Link
                className="text-primary hover:underline"
                to="/projects/$project/dashboard"
                params={{ project: destination }}
              >
                {destination}
              </Link>
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Started {new Date(job.created_at).toLocaleString()}
            {job.created_by ? ` by ${job.created_by}` : ""}, last update {new Date(job.updated_at).toLocaleString()}
          </p>
          <JobStatus user={user} jobId={jobId} />
        </div>
      </div>
    </div>
  );
}
