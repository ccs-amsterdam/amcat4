import { useArticles } from "@/api/articles";
import { useFieldStats } from "@/api/fieldStats";
import { useFields } from "@/api/fields";
import { useHasProjectRole } from "@/api/project";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { AggregationAxis, AmcatField, AmcatProjectId, AmcatQuery, AmcatUserRole } from "@/interfaces";
import { autoFormatDate } from "@/lib/autoFormatDate";
import { hasMinAmcatRole } from "@/lib/utils";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, Columns3Cog, DatabaseZap, LayoutDashboard, LockKeyholeOpen, Settings, Users } from "lucide-react";
import { useMemo } from "react";
import AggregateResult from "../Aggregate/AggregateResult";
import Articles from "../Articles/Articles";
import CodeExample from "../CodeExample/CodeExample";
import { Loading } from "../ui/loading";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function Summary({ user, projectId, query }: Props) {
  const { data: fields } = useFields(user, projectId);
  const isWriter = useHasProjectRole(user, projectId, "WRITER");
  const { data, isError, error } = useArticles(user, projectId, query);
  if (isError) {
    const message = (error as any)?.response?.data?.detail ?? "Search failed";
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>{message}</span>
      </div>
    );
  }
  if (data == null) return null;

  function renderVisualization(field: AmcatField) {
    if (!field.client_settings.inListSummary) return null;
    if (field.type === "number" || field.type === "integer")
      return <LineSummaryGraph key={field.name} user={user} projectId={projectId} query={query} field={field} />;
    if (field.type === "date")
      return <DateSummaryGraph key={field.name} user={user} projectId={projectId} query={query} field={field} />;
    if (field.type === "keyword")
      return <KeywordSummaryGraph key={field.name} user={user} projectId={projectId} query={query} field={field} />;
  }

  const visualizations = (fields || []).map(renderVisualization).filter((el) => el != null);
  return (
    <div className="grid snap-x snap-mandatory grid-cols-[100%,100%] gap-1 overflow-auto md:grid-cols-2 md:gap-3 md:overflow-visible">
      <div className="border-foreground/31 snap-center  rounded-l">
        <Articles
          user={user}
          projectId={projectId}
          query={query}
          headerRight={<CodeExample action="search" projectId={projectId} query={query} />}
        />
      </div>
      <div className="mt-12 flex snap-center flex-col  gap-3 md:gap-6">
        {visualizations.length === 0 ? (
          <div className="w-full flex-auto px-10 py-14 text-right text-xl text-primary">
            {isWriter ? <a href="./fields">Enable visualizations in field settings</a> : null}
          </div>
        ) : (
          visualizations
        )}
      </div>
    </div>
  );
}

interface SummaryProps extends Props {
  field: AmcatField;
}

function DateSummaryGraph({ user, projectId, query, field }: SummaryProps) {
  const { data: values, isLoading: valuesLoading } = useFieldStats(user, projectId, field.name);

  const [axes, interval] = useMemo(() => {
    if (!values?.max_as_string || !values.min_as_string) return [[], null];
    let minTime = new Date(values.min_as_string).getTime();
    let maxTime = new Date(values.max_as_string).getTime();

    if (query.filters && field.name in query.filters) {
      // if there is a filter on this field, use that to set the min and max time
      const filter = query.filters[field.name];
      if (filter.gt) minTime = Math.max(minTime, new Date(filter.gt).getTime());
      if (filter.gte) minTime = Math.max(minTime, new Date(filter.gte).getTime());
      if (filter.lt) maxTime = Math.min(maxTime, new Date(filter.lt).getTime());
      if (filter.lte) maxTime = Math.min(maxTime, new Date(filter.lte).getTime());
    }
    const interval = autoFormatDate(minTime, maxTime, 20);
    const axes: AggregationAxis[] = [{ name: field.name, field: field.name, interval }];
    if (query.queries && query.queries.length > 0) axes.push({ name: "_query", field: "_query" });
    return [axes, interval];
  }, [values, field, query]);

  if (valuesLoading) return <Loading />;
  if (!values) return null;

  const title = interval ? `${field.name.toUpperCase()} - ${interval}` : field.name.toUpperCase();

  return (
    <AggregateResult
      user={user}
      projectId={projectId}
      query={query}
      options={{ axes, display: "linechart", title }}
      defaultPageSize={200}
    />
  );
}

function LineSummaryGraph({ user, projectId, query, field }: SummaryProps) {
  const { data: values, isLoading: valuesLoading } = useFieldStats(user, projectId, field.name);

  const axes: AggregationAxis[] = useMemo(() => {
    return [{ name: field.name, field: field.name }];
  }, [field]);

  if (valuesLoading) return <Loading />;
  if (!values) return null;

  const title = field.name.toUpperCase();

  return (
    <AggregateResult
      user={user}
      projectId={projectId}
      query={query}
      options={{ axes, display: "linechart", title }}
      defaultPageSize={200}
    />
  );
}

function KeywordSummaryGraph({ user, projectId, query, field }: SummaryProps) {
  const axes = useMemo(() => {
    const axes: AggregationAxis[] = [{ name: field.name, field: field.name }];
    if (query.queries && query.queries.length > 0) axes.push({ name: "_query", field: "_query" });
    return axes;
  }, [field, query]);

  return (
    <AggregateResult
      user={user}
      projectId={projectId}
      query={query}
      options={{ axes, display: "barchart", title: field.name.toUpperCase() }}
      defaultPageSize={20}
    />
  );
}

export function EmptyProject({ projectId, role }: { projectId: AmcatProjectId; role: AmcatUserRole }) {
  const isAdmin = role === "ADMIN";
  const isWriter = hasMinAmcatRole(role, "WRITER");

  const tabs = [
    {
      to: "/projects/$project/dashboard" as const,
      Icon: LayoutDashboard,
      label: "Dashboard",
      description: "Search, aggregate, and download documents",
      show: true,
    },
    {
      to: "/projects/$project/data" as const,
      Icon: DatabaseZap,
      label: "Data",
      description: "Upload documents from a CSV file",
      show: isWriter,
    },
    {
      to: "/projects/$project/fields" as const,
      Icon: Columns3Cog,
      label: "Fields",
      description: "Configure the fields for each document in this project",
      show: isWriter,
    },
    {
      to: "/projects/$project/users" as const,
      Icon: Users,
      label: "Users",
      description: "Invite collaborators and set a guest role for public access",
      show: isAdmin,
    },
    {
      to: "/projects/$project/settings" as const,
      Icon: Settings,
      label: "Settings",
      description: isAdmin
        ? "Update the project name, description, and other details"
        : "View project information and settings",
      show: true,
    },
    {
      to: "/projects/$project/access" as const,
      Icon: LockKeyholeOpen,
      label: "Access",
      description: "View your access level or request additional permissions",
      show: !isAdmin,
    },
  ].filter((t) => t.show);

  return (
    <div className="w-full rounded bg-primary/10 p-6">
      <div className="prose dark:prose-invert">
        <h3>This project is empty</h3>
        <p>
          {isAdmin
            ? "Congratulations on creating a project! Here are some actions you can take to get started:"
            : "This project doesn't have any data yet. Here is an overview of what you can do:"}
          <ul className="not-prose flex flex-col gap-3 py-2">
            {tabs.map(({ to, Icon, label, description }) => (
              <li key={to} className="flex items-center gap-3">
                <Link to={to} params={{ project: projectId }} className="flex items-center gap-2 font-medium no-underline hover:underline">
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </Link>
                <span className="text-foreground/70">— {description}</span>
              </li>
            ))}
          </ul>
        </p>
        {isWriter && (
          <p className="mt-4 text-sm">
            As soon as you add data to the project, you will be taken to the Dashboard where you can search, aggregate, and download documents.
          </p>
        )}
        {isWriter && (
          <p className="mt-4 text-sm">
            You can also connect to this project from{" "}
            <a href="https://github.com/ccs-amsterdam/amcat4py" target="_blank" rel="noreferrer">Python</a>
            {" "}or{" "}
            <a href="https://github.com/ccs-amsterdam/amcat4r" target="_blank" rel="noreferrer">R</a>
            {" "}to upload or query documents from a script.
          </p>
        )}
      </div>
    </div>
  );
}
