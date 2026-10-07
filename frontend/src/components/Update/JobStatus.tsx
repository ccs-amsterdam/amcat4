import { jobIsActive, useCancelJob, useJob } from "@/api/jobs";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { AlertCircle, Ban, CheckCircle, Loader } from "lucide-react";
import { Button } from "../ui/button";
import { Loading } from "../ui/loading";
import { Progress } from "../ui/progress";

interface Props {
  user: AmcatSessionUser;
  jobId: string;
}

/**
 * Show the status and progress of a background job (polling while it is pending or running),
 * with a button to cancel it
 */
export default function JobStatus({ user, jobId }: Props) {
  const { data: job, isLoading } = useJob(user, jobId);
  const { mutate: cancelJob, isPending: cancelling } = useCancelJob(user);

  if (isLoading) return <Loading msg="Loading job status" />;
  if (!job) return null;

  const active = jobIsActive(job);
  const total = job.progress?.total;
  const copied = job.result?.copied ?? job.progress?.copied ?? 0;
  const progressValue = total ? Math.round((copied / total) * 100) : job.status === "done" ? 100 : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2 text-sm font-medium">
          {job.status === "failed" ? (
            <>
              <AlertCircle className="h-4 w-4 text-destructive" />
              <span className="text-destructive">Failed</span>
            </>
          ) : job.status === "cancelled" ? (
            <>
              <Ban className="h-4 w-4 text-yellow-500" />
              <span className="text-yellow-600">Cancelled</span>
            </>
          ) : job.status === "done" ? (
            <>
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-green-600">Completed</span>
            </>
          ) : (
            <>
              <Loader className="h-4 w-4 animate-spin text-primary" />
              <span className="text-muted-foreground">{job.status === "pending" ? "Waiting to start…" : "In progress…"}</span>
            </>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {copied.toLocaleString()}
          {total != null ? ` / ${total.toLocaleString()}` : ""} documents copied
        </div>
      </div>

      <div className={active && !total ? "animate-pulse" : ""}>
        <Progress value={progressValue} className="h-2" />
      </div>

      {job.error && <p className="text-xs text-destructive">{job.error}</p>}

      {active && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            The copy is running in the background. You can close this page and the copying will continue.
          </p>
          <Button variant="outline" size="sm" disabled={cancelling} onClick={() => cancelJob(job.id)}>
            Cancel
          </Button>
        </div>
      )}
      {job.status === "cancelled" && (
        <p className="text-xs text-muted-foreground">Documents that were already copied are not removed.</p>
      )}
    </div>
  );
}
