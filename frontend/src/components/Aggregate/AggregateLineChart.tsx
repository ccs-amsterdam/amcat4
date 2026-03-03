import { AggregateVisualizerProps } from "@/interfaces";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CustomTooltip } from "./CustomTooltip";
import { qualitativeColors } from "./colors";

import { useState } from "react";

export default function AggregateLineChart({ data, createZoom, width, height, limit }: AggregateVisualizerProps) {
  const [line, setLine] = useState<string>("");

  if (!data) return null;

  const colors = qualitativeColors(data.columns.length);

  const handleClick = (x: number) => {
    if (!data.axes[0].name) return;

    // First value is always the payload for primary aggregation axis
    const values: (number | string)[] = [data.rows[x][data.axes[0].name]];
    if (data.axes.length !== 1) {
      if (!line) return;
      // Second value is the name of the line clicked on
      values.push(line);
    }

    createZoom(values);
  };

  if (height == null) height = 300;
  if (width == null) width = "100%";
  return (
    <div>
      <ResponsiveContainer height={height} width={width} className="text-sm">
        <LineChart
          style={{ cursor: "pointer" }}
          data={data.rows}
          onClick={(e) => handleClick(e.activeTooltipIndex || 0)}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={data.axes[0].name} />
          <YAxis domain={[0, data.domain[1]]} />
          <Tooltip trigger={"hover"} content={<CustomTooltip value={line} onChangeGroup={setLine} />} />
          {data.axes.length > 1 ? <Legend /> : null}
          {data.columns.map((column, i) => (
            <Line
              key={column.name + i}
              type="monotone"
              dataKey={column.name}
              stroke={colors[i]}
              activeDot={{ style: { cursor: "pointer" } }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
