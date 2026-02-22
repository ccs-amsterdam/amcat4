import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AggregateVisualizerProps } from "@/interfaces";
import AggregateList from "./AggregateList";

export default function AggregateTable({ data, createZoom, limit }: AggregateVisualizerProps) {
  // A table without columns is the same as a list (not trying to get metaphysical here)
  const primary = data.axes[0];
  const secondary = data.axes[1];
  if (!secondary) return AggregateList({ data, createZoom, limit });

  let rowset = new Set();
  let colset = new Set();
  const d: { [key: string]: { [key: string]: number } } = {};
  data.rows.forEach((row) => {
    const rowName = String(row[primary.field]);
    const colName = String(row[secondary.field]);
    rowset.add(rowName);
    colset.add(colName);
    d[rowName] = { ...d[rowName], [colName]: Number(row["n"]) };
  });

  //const cols = Array.from(colset.values()).sort() as string[];
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>
            <TableCaption></TableCaption>
          </TableHead>
          {data.columns.map((column) => {
            return (
              <TableHead key={column.name}>
                <TableCaption>{column.name}</TableCaption>
              </TableHead>
            );
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.rows.map((row) => {
          return (
            <TableRow key={row[primary.name]}>
              <TableCell>{row[primary.name]}</TableCell>
              {data.columns.map((column) => {
                return (
                  <TableCell className="hover:bg-primary" key={column.name}>
                    {row[column.name] || 0}
                  </TableCell>
                );
              })}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
