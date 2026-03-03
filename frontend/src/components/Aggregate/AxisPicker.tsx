import { AmcatField, AggregationAxis, AggregationInterval } from "@/interfaces";
import { getField } from "@/api/fields";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const date_intervals = [
  { key: "day", text: "Day", value: "day" },
  { key: "week", text: "Week", value: "week" },
  { key: "month", text: "Month", value: "month" },
  { key: "quarter", text: "Quarter", value: "quarter" },
  { key: "year", text: "Year", value: "year" },
  { key: "dayofweek", text: "Day of week", value: "dayofweek" },
  { key: "daypart", text: "Part of day", value: "daypart" },
  { key: "monthnr", text: "Month number", value: "monthnr" },
  { key: "yearnr", text: "Year Number", value: "yearnr" },
  { key: "decade", text: "Decade", value: "decade" },
  { key: "dayofmonth", text: "Day of Month", value: "dayofmonth" },
  { key: "weeknr", text: "Week Number", value: "weeknr" },
];

interface AxisPickerProps {
  /** project fields to choose from */
  fields: AmcatField[];
  /** Current axis value */
  value: AggregationAxis;
  /** Add 'by query' option? */
  byQuery?: boolean;
  /** Callback to set axis when user changes field or interval */
  onChange: (value: AggregationAxis) => void;
  label?: string;
}

/**
 * Dropdown to select an aggregation axis and possibly interval
 */
export default function AxisPicker({ fields, value, onChange, label, byQuery = false }: AxisPickerProps) {
  const axisOptions = fields
    .filter((f) => ["keyword", "tag", "date"].includes(f.type))
    .map((f) => ({
      key: f.name,
      text: f.name,
      value: f.name,
      icon: f.type === "date" ? "calendar outline" : "list",
    }));
  if (byQuery)
    axisOptions.unshift({
      key: "_query",
      text: "By query",
      value: "_query",
      icon: "",
    });

  const setInterval = (newval: AggregationInterval) => {
    onChange({ ...value, interval: newval });
  };
  const setField = (newval: string) => {
    // I don't know why the name of the field was not included here.
    // currently refactoring so that aggregationaxis always has a name,
    // but don't know the consequences yet
    const f = newval === "_query" ? { name: "", type: "_query" } : getField(fields, newval);
    if (!f) return;
    const interval = f.type === "date" ? value?.interval : undefined;
    onChange({ name: f.name, interval: interval, field: f.type });
  };
  const field = getField(fields, value.field);

  return (
    <div>
      <Select onValueChange={(value) => setField(String(value))} value={field?.name}>
        <SelectTrigger>
          <SelectValue placeholder="Select field for aggregation axis" />
        </SelectTrigger>
        <SelectContent>
          {axisOptions.map((option) => {
            return (
              <SelectItem key={option.key} value={option.value}>
                {option.text}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>

      {field?.type === "date" ? (
        <Select onValueChange={(value) => setInterval(value as AggregationInterval)} value={value?.interval}>
          <SelectTrigger>
            <SelectValue placeholder="Select interval for date aggregation" />
          </SelectTrigger>
          <SelectContent>
            {date_intervals.map((option) => {
              return (
                <SelectItem key={option.key} value={option.value}>
                  {option.text}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      ) : null}
    </div>
  );
}
