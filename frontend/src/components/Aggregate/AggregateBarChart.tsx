import { Legend, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AggregateVisualizerProps } from "@/interfaces";
import { qualitativeColors } from "./colors";
import { CustomTooltip } from "./CustomTooltip";
import { useState } from "react";

export default function AggregateBarChart({ data, createZoom, width, height, limit }: AggregateVisualizerProps) {
  if (!data) return null;
  const [bar, setBar] = useState<string>("");

  const colors = qualitativeColors(data.columns.length);
  const primary = data.axes[0].name;

  const handleClick = (column: string, j: number) => {
    if (createZoom == null) return;

    // First value is always the value for primary axis on the clicked "row"
    const values = [data.rows[j][primary]];
    if (data.axes.length !== 1) {
      if (!bar) return;
      // Second value is the bar clicked on
      values.push(column);
    }

    createZoom(values);
  };

  if (height == null) height = Math.max(250, data.rows.length * 30);
  if (width == null) width = "100%";

  return (
    <ResponsiveContainer width={width} height={height} className="text-sm ">
      <BarChart data={data.rows} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" />
        <YAxis
          type="category"
          dataKey={primary}
          width={250}
          interval={0}
          fontSize={12}
          tickFormatter={(value) =>
            typeof value === "string" && value.length > 30 ? value.slice(0, 27) + "..." : value
          }
        />
        <XAxis type="number" domain={[0, data.domain[1]]} />
        <Tooltip cursor={{ opacity: 0.2 }} content={<CustomTooltip value={bar} />} />

        {data.axes.length > 1 ? <Legend /> : null}
        {data.columns.map((column, i) => (
          <Bar
            key={i}
            className="cursor-pointer"
            type="monotone"
            dataKey={column.name}
            barSize={12}
            fill={colors[i]}
            onMouseEnter={() => setBar(column.name)}
            onClick={(e, j) => handleClick(column.name, j)}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
