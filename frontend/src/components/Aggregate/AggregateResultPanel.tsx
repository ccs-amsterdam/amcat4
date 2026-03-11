import { AggregationOptions, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
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

  function defaultPageSize() {
    if (options.display === "linechart") return 200;
    if (options.display === "barchart") return 20;
    if (options.display === "table") return 50;
    if (options.display === "list") return 20;
  }

  if (!user || !projectId || !query) return null;

  return (
    <div>
      <div className="prose p-5 pb-0 dark:prose-invert">
        <h3>Aggregate</h3>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[auto,1fr]">
        <div className="flex justify-center p-5">
          <AggregateResultOptions
            user={user}
            projectId={projectId}
            query={query}
            options={options}
            setOptions={setOptions}
          />
        </div>
        <div className="w-full p-5">
          {options.axes.length === 0 ? (
            <div className="prose dark:prose-invert max-w-prose mt-4">
              <p>
                The aggregate tab groups documents by one or two fields and visualizes the result. Configure the options
                on the left and click <strong>Submit</strong> to run.
              </p>
              <ul>
                <li>
                  <strong>Display</strong> — choose how to visualize the result: a line graph or bar chart for trends
                  over time, a table for cross-tabulations, or a list for ranked counts.
                </li>
                <li>
                  <strong>Aggregate</strong> — what to measure. Defaults to <em>Count</em> (number of documents), but
                  you can also compute the sum, average, minimum, or maximum of a numeric field.
                </li>
                <li>
                  <strong>Axis</strong> — the field to group by, such as a date (with an interval like week or month),
                  a keyword, or a tag. A second axis is optional and adds a further grouping dimension (e.g. multiple
                  lines in a line graph).
                </li>
              </ul>
            </div>
          ) : (
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
    </div>
  );
}
