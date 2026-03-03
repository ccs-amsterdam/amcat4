import { AggregateDataPoint, AggregateVisualizerProps } from "@/interfaces";
import { axis_label } from "./createChartData";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function AggregateList({ data, createZoom, limit }: AggregateVisualizerProps) {
  const handleClick = (row: AggregateDataPoint) => {
    const values = data.axes.map((axis) => row[axis.field]);

    createZoom(values);
  };
  let d: AggregateDataPoint[] = data.rows;

  if (limit && d.length > limit) d = d.slice(0, limit);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {data.axes.map((axis, i) => (
            <TableHead key={i}>{axis_label(axis)}</TableHead>
          ))}
          <TableHead>N</TableHead>
          {data.aggregations?.map((metric, i) => <TableHead key={-i}>{metric.name}</TableHead>)}
        </TableRow>
      </TableHeader>
      <TableBody>
        {d.map((row, i) => {
          return (
            <TableRow key={i}>
              {data.axes.map((axis, j) => {
                if (!axis.name) return null;
                return (
                  <TableCell key={j} onClick={() => handleClick(row)}>
                    {row[axis.name]}
                  </TableCell>
                );
              })}
              <TableCell>{row.n}</TableCell>

              {data.aggregations?.map((metric, i: number) => {
                if (!metric.name) return null;
                return <TableCell key={-i}>{row[metric.name]}</TableCell>;
              })}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
