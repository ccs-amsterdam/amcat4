import { AggregateData, AggregateDataPoint, AggregationAxis, AggregationInterval, ChartData } from "@/interfaces";
import { qualitativeColors } from "./colors";

// Convert amcat aggregate results ('long' format data plus axes) into data for recharts ('wide' data and series names)
// Specifically, from [{ row_id, col_id, value }, ...] to [{ row_id, col1: value1, col2: value2, ...}, ...]
export function createChartData(data: AggregateData, sorted?: boolean): ChartData {
  const fields = data.meta.axes.map((axis) => axis.name);
  const target = data.meta.aggregations.length > 0 ? data.meta.aggregations[0].name || "n" : "n";
  const interval = data.meta.axes[0].interval;

  let rows = data.data;
  let columnNames = [target];
  if (fields.length > 1) {
    const wideData = longToWide(data.data, data.meta.axes[0], data.meta.axes[1], target, interval);
    rows = wideData.rows;
    columnNames = wideData.columnNames;
  }

  const { columns, domain } = computeChartDataStatistics(rows, columnNames);
  rows = add_zeroes(rows, fields[0], interval, columnNames);

  if (data.meta.axes[0].interval) {
    rows = rows
      .map((x) => transform_dateparts(x, data.meta.axes[0]))
      .sort((e1, e2) => e1._sort - e2._sort)
      .map((row) => {
        const { _sort, ...columns } = row;
        return columns;
      });
  } else {
    if (sorted) {
      rows = rows.sort((e1, e2) => {
        let sum1 = 0;
        let sum2 = 0;
        for (const column of columns) {
          sum1 += Number(e1[column.name]) || 0;
          sum2 += Number(e2[column.name]) || 0;
        }
        return sum2 - sum1;
      });
    }
  }

  return { rows, columns, domain, axes: data.meta.axes, aggregations: data.meta.aggregations };
}

/*
 * If there is a secondary axis, we pivot the data so that the secondary
 * axis becomes the columns of the table.
 */
function longToWide(
  data: AggregateDataPoint[],
  primary: AggregationAxis,
  secondary: AggregationAxis,
  target: string,
  interval?: AggregationInterval,
) {
  // convert results from amcat to wide format
  const t_col = (val: any) =>
    secondary.interval && can_transform(secondary.interval)
      ? transform_datepart_value(val, secondary.interval).label
      : val;
  const columnNames = Array.from(new Set(data.map((row) => String(t_col(row[secondary.name])))));
  const dmap = new Map(
    data.map((p) => [JSON.stringify([p[primary.name], t_col(p[secondary.name])]), Number(p[target])]),
  );
  let rowNames = Array.from(new Set(data.map((row) => String(row[primary.name]))));
  if (interval === "year") rowNames = daterange(rowNames, interval);

  const rows = rowNames.map((rowName) => {
    const row: Record<string, string | number> = { [primary.name]: rowName };
    columnNames.forEach((colName) => {
      const key = JSON.stringify([rowName, colName]);
      row[colName] = dmap.get(key) ?? 0;
    });
    return row;
  });
  return { rows, columnNames };
}

function computeChartDataStatistics(rows: AggregateDataPoint[], columnNames: string[]) {
  const colors = qualitativeColors(columnNames.length);
  const firstValue = Number(rows[0][columnNames[0]]);
  const domain: [number, number] = [firstValue, firstValue];
  const columns = columnNames.map((name, i) => {
    let sum = 0;
    for (const row of rows) {
      const value = Number(row[name]);
      sum += value;
      if (value > domain[1]) domain[1] = value;
      if (value < domain[0]) domain[0] = value;
    }
    return { name, sum, color: colors[i % colors.length] };
  });
  return { columns, domain };
}

function ymd(d: Date): string {
  // We use a custom function because toIsoDate (1) includes time, and
  // (2) changes the date to what it would be in UTC time zone, potentially changing the day
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function add_zeroes(
  d: AggregateDataPoint[],
  field: string,
  interval: AggregationInterval | undefined,
  columnNames: string[],
): AggregateDataPoint[] {
  if (!interval) return d;

  const zeroes = Object.fromEntries(columnNames.map((colName) => [colName, 0]));

  if (["year", "quarter", "month", "week", "day"].includes(interval)) {
    const domainMap = new Map(d.map((p) => [ymd(new Date(p[field])), p]));
    const domain = daterange(
      d.map((p) => String(p[field])),
      interval,
    );
    return domain.map((x) => domainMap.get(x) || { [field]: x, ...zeroes });
  }

  function byDomain(d: AggregateDataPoint[], domain: string[]) {
    const domainMap = new Map(d.map((p) => [String(p[field]), p]));
    return domain.map((x) => domainMap.get(x) || { [field]: x, ...zeroes });
  }

  if (interval === "monthnr") return byDomain(d, [...MONTHS.keys()]);
  if (interval === "dayofweek") return byDomain(d, [...DATEPARTS_DOW.keys()]);
  if (interval === "daypart") return byDomain(d, [...DATEPARTS_DAYPART.keys()]);

  function byYearNrDomain(d: AggregateDataPoint[], decade: boolean = false) {
    const years = d.map((p) => Number(p[field])).filter((y) => !isNaN(y));
    if (years.length === 0) return [];
    let min = Math.min(...years);
    let max = Math.max(...years);
    if (decade) {
      min = Math.floor(min / 10) * 10;
      max = Math.floor(max / 10) * 10;
    }
    const result: string[] = [];
    for (let y = min; y <= max; decade ? (y += 10) : y++) {
      result.push(String(y));
    }
    return result;
  }

  if (interval === "yearnr") return byDomain(d, byYearNrDomain(d, false));
  if (interval === "decade") return byDomain(d, byYearNrDomain(d, true));

  return d;
}

function incrementDate(date: Date, interval: AggregationInterval) {
  const y = date.getFullYear();
  const m = date.getMonth();
  const d = date.getDate();

  switch (interval) {
    case "year":
      return new Date(y + 1, m, d);
    case "quarter":
      return new Date(y, m + 3, d);
    case "month":
      return new Date(y, m + 1, d);
    case "week":
      return new Date(y, m, d + 7);
    case "day":
      return new Date(y, m, d + 1);
    default:
      throw new Error(`Can't handle interval ${interval}, sorry!`);
  }
}

function daterange(values: string[], interval: AggregationInterval): string[] {
  if (interval === "monthnr") {
    return values;
  }
  const result: string[] = [];
  const dates = values.map((d) => new Date(d));
  if (values.length === 0) return result;
  let d = dates.reduce((a, b) => (a < b ? a : b));
  const enddate = dates.reduce((a, b) => (a > b ? a : b));
  while (d <= enddate) {
    result.push(ymd(d));
    d = incrementDate(d, interval);
  }
  return result;
}

const DATEPARTS_DOW = new Map([
  ["Monday", { label: "Monday", _sort: 1 }],
  ["Tuesday", { label: "Tuesday", _sort: 2 }],
  ["Wednesday", { label: "Wednesday", _sort: 3 }],
  ["Thursday", { label: "Thursday", _sort: 4 }],
  ["Friday", { label: "Friday", _sort: 5 }],
  ["Saturday", { label: "Saturday", _sort: 6 }],
  ["Sunday", { label: "Sunday", _sort: 7 }],
]);

const DATEPARTS_DAYPART = new Map([
  ["Morning", { label: "Morning", _sort: 1 }],
  ["Afternoon", { label: "Afternoon", _sort: 2 }],
  ["Evening", { label: "Evening", _sort: 3 }],
  ["Night", { label: "Night", _sort: 4 }],
]);

const MONTHS = new Map([
  ["1", { label: "January", _sort: 1 }],
  ["2", { label: "February", _sort: 2 }],
  ["3", { label: "March", _sort: 3 }],
  ["4", { label: "April", _sort: 4 }],
  ["5", { label: "May", _sort: 5 }],
  ["6", { label: "June", _sort: 6 }],
  ["7", { label: "July", _sort: 7 }],
  ["8", { label: "August", _sort: 8 }],
  ["9", { label: "September", _sort: 9 }],
  ["10", { label: "October", _sort: 10 }],
  ["11", { label: "November", _sort: 11 }],
  ["12", { label: "December", _sort: 12 }],
]);

function transform_datepart_value(value: string | number, interval: AggregationInterval | undefined) {
  const def = { label: String(value), _sort: 0 }; // sort 0 uses order returned by AmCAT
  switch (interval) {
    case "dayofweek":
      return DATEPARTS_DOW.get(String(value)) || def;
    case "daypart":
      return DATEPARTS_DAYPART.get(String(value)) || def;
    case "monthnr":
      return MONTHS.get(String(value)) || def;
    default:
      return def;
  }
}

function transform_dateparts(x: AggregateDataPoint, axis: AggregationAxis) {
  const dp = transform_datepart_value(x[axis.name], axis.interval);
  return { ...x, [axis.name]: dp.label, _sort: dp._sort };
}

function can_transform(interval: string | undefined): boolean {
  if (!interval) return false;
  return ["dayofweek", "daypart", "monthnr"].includes(interval);
}

export function axis_label(axis: AggregationAxis): string {
  if (axis.interval) return `${axis.field} (${INTERVAL_LABELS.get(axis.interval)})`;
  return axis.name;
}

const INTERVAL_LABELS = new Map([
  ["day", "Day"],
  ["week", "Week"],
  ["month", "Month"],
  ["quarter", "Quarter"],
  ["year", "Year"],
  ["dayofweek", "Day of week"],
  ["daypart", "Part of day"],
  ["monthnr", "Month number"],
  ["yearnr", "Year Number"],
  ["decade", "Decade"],
  ["dayofmonth", "Day of Month"],
  ["weeknr", "Week Number"],
]);
