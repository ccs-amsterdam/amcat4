import { useHasProjectRole } from "@/api/project";
import { useArticles } from "@/api/articles";
import { useFieldStats } from "@/api/fieldStats";
import { useFields } from "@/api/fields";
import { AggregationAxis, AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { autoFormatDate } from "@/lib/autoFormatDate";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useMemo } from "react";
import AggregateResult from "../Aggregate/AggregateResult";
import Articles from "../Articles/Articles";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function Summary({ user, projectId, query }: Props) {
  const { data: fields } = useFields(user, projectId);
  const isWriter = useHasProjectRole(user, projectId, "WRITER");
  const { data } = useArticles(user, projectId, query);
  if (data == null) return null;

  const isEmpty = data.pages[0].meta.total_count === 0;
  if (isEmpty) return <EmptyProject />;

  function renderVisualization(field: AmcatField) {
    if (!field.client_settings.inListSummary) return null;
    if (field.type === "date")
      return <DateSummaryGraph key={field.name} user={user} projectId={projectId} query={query} field={field} />;
    if (field.type === "keyword")
      return <KeywordSummaryGraph key={field.name} user={user} projectId={projectId} query={query} field={field} />;
  }

  const visualizations = (fields || []).map(renderVisualization).filter((el) => el != null);
  return (
    <div className="grid snap-x snap-mandatory grid-cols-[100%,100%] gap-1 overflow-auto md:grid-cols-2 md:gap-3 md:overflow-visible">
      <div className="border-foreground/31 snap-center  rounded-l">
        <Articles user={user} projectId={projectId} query={query} />
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

  if (valuesLoading) return <div>Loading...</div>;
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

function EmptyProject() {
  return (
    <div className="w-full rounded bg-primary/10 p-3">
      <div className="prose dark:prose-invert">
        <h3>This project is empty</h3>
        <p>
          Congratulations on creating a project! To add documents, you can use the CSV uploader in the 'Data' menu
          above. You can also use the API from R or Python for more powerful upload options
        </p>
      </div>
    </div>
  );
}
