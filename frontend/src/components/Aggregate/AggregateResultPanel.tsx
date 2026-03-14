import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { InfoBox } from "@/components/ui/info-box";
import { AggregationOptions, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { useState } from "react";
import CodeExample from "../CodeExample/CodeExample";
import AggregateResult from "./AggregateResult";
import { AggregateResultOptions } from "./AggregateResultOptions";

const initialState: AggregationOptions = {
  display: "linechart",
  axes: [],
};

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function AggregateResultPanel({ user, projectId, query }: Props) {
  const [options, setOptions] = useState<AggregationOptions>(initialState);
  const [liveOptions, setLiveOptions] = useState<AggregationOptions>(initialState);

  function defaultPageSize() {
    if (options.display === "linechart") return 200;
    if (options.display === "barchart") return 20;
    if (options.display === "table") return 50;
    if (options.display === "list") return 20;
  }

  if (!user || !projectId || !query) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="prose p-5 pb-0 dark:prose-invert flex items-center justify-between">
        <h3>Aggregate</h3>
        <CodeExample action="aggregate" projectId={projectId} query={query} options={liveOptions} />
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[auto,1fr]">
        <div className="flex justify-center p-5">
          <AggregateResultOptions
            user={user}
            projectId={projectId}
            query={query}
            options={options}
            setOptions={setOptions}
            onOptionsChange={setLiveOptions}
          />
        </div>
        <div className="w-full p-5">
          {options.axes.length > 0 && (
            <AggregateResult
              user={user}
              projectId={projectId}
              query={query}
              options={options}
              defaultPageSize={defaultPageSize()}
            />
          )}
        </div>
      </div>
      <div className="px-5 pb-5">
        <InfoBox title="Information on aggregation" storageKey="infobox:aggregate">
          <div className="flex flex-col gap-3 text-sm">
            <p>
              The aggregate tab groups documents by one or two fields and visualizes the result. Configure the options
              on the left and click <strong className="text-foreground">Submit</strong> to run.
            </p>
            <div className="rounded-md bg-primary/10 p-3">
              <div className="grid grid-cols-[5rem_1fr] gap-3">
                <b className="text-primary">Display</b>
                Choose how to visualize the result: a line graph or bar chart for trends over time, a table for cross-tabulations, or a list for ranked counts.
                <b className="text-primary">Aggregate</b>
                <span>What to measure. Defaults to <em>Count</em> (number of documents), but you can also compute the sum, average, minimum, or maximum of a numeric field.</span>
                <b className="text-primary">Axis</b>
                The field to group by, such as a date (with an interval like week or month), a keyword, or a tag. A second axis is optional and adds a further grouping dimension (e.g. multiple lines in a line graph).
              </div>
            </div>
          </div>
        </InfoBox>
      </div>
    </div>
  );
}
