import { useFieldStats } from "@/api/fieldStats";
import { useFieldValues } from "@/api/fieldValues";
import { Checkbox } from "@/components/ui/checkbox";
import { AmcatField, AmcatFilter, AmcatProjectId, DateFilter } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useMemo, useRef, useState } from "react";
import { Input } from "../ui/input";
import DatePicker from "./DatePicker";

interface FilterPopupProps {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  field: AmcatField | undefined;
  value: AmcatFilter | undefined;
  onChange: (value: AmcatFilter) => void;
}

export function filterLabel(name: string, field: AmcatField | undefined, filter: AmcatFilter | undefined) {
  if (filter == null) return name;

  let values = "";
  if (field?.type === "date") {
    if (filter.gte && filter.lte) values = `${filter.gte} / ${filter.lte}`;
    if (filter.gte && !filter.lte) values = `from ${filter.gte}`;
    if (filter.lte && !filter.gte) values = `until ${filter.lte}`;
  } else {
    if (filter.values && filter.values.length > 0) {
      values = `(${filter.values.length})`;
    }
  }

  if (values)
    return (
      <div className="flex w-full items-center gap-2">
        <div className="font-bold">{name}</div>
        <span className="">{values}</span>
      </div>
    );

  return (
    <span>
      select <b>{name}</b>
    </span>
  );
}

export function FilterPopup({ user, projectId, field, value, onChange }: FilterPopupProps) {
  if (field == null || value == null) return null;

  if (field.type === "date") return DateRangePopup({ user, projectId, field, value, onChange });
  if (field.type === "number") return NumberRangePopup({ user, projectId, field, value, onChange });
  return KeywordPopup({ user, projectId, field, value, onChange });
}

function NumberRangePopup({ user, projectId, field, value, onChange }: FilterPopupProps) {
  const { data: fieldStats } = useFieldStats(user, projectId, field?.name);

  if (field == null || value == null || fieldStats == null) return null;
  return (
    <div>
      <div className="grid grid-cols-1 gap-4">
        <div className="grid grid-cols-[4rem,10rem] items-center">
          <label>from</label>
          <Input
            type="number"
            min={fieldStats.min ?? undefined}
            value={Number(value.gte) || (fieldStats.min ?? undefined)}
            onChange={(e) => onChange({ gte: String(e.target.value), lte: value.lte })}
          />
        </div>
        <div className="grid grid-cols-[4rem,10rem] items-center">
          <label>to</label>
          <Input
            type="number"
            max={fieldStats.max ?? undefined}
            value={Number(value.lte) || (fieldStats.max ?? undefined)}
            onChange={(e) => onChange({ gte: value.gte, lte: String(e.target.value) })}
          />
        </div>
      </div>
    </div>
  );
}

function KeywordPopup({ user, projectId, field, value, onChange }: FilterPopupProps) {
  const [query, setQuery] = useState("");
  const { data: fieldValues } = useFieldValues(user, projectId, field?.name);
  const enableSearch = fieldValues && fieldValues?.length > 10;
  const selected = value?.values || [];

  // this way the order of showValues doesn't immediately change on select/deselect
  const selectedRef = useRef<(string | number)[]>(undefined);
  selectedRef.current = selected;

  const showValues = useMemo(() => {
    const selectedValues: string[] = [];
    const unselectedValues: string[] = [];
    for (let v of fieldValues || []) {
      if (query && !v.toLowerCase().includes(query.toLowerCase())) continue;
      if (selectedRef?.current?.includes(v)) {
        selectedValues.push(v);
      } else {
        unselectedValues.push(v);
      }
    }
    const showValues = [...selectedValues, ...unselectedValues];
    return showValues.slice(0, 200);
  }, [fieldValues, selectedRef, query]);

  if (field == null || value == null) return null;
  if (!fieldValues || fieldValues.length === 0) return null;

  function handleChange(checked: boolean, v: string) {
    if (checked && !selected.includes(v)) onChange({ values: [...selected, v] });
    if (!checked && selected.includes(v)) onChange({ values: selected.filter((x) => x !== v) });
  }

  return (
    <div>
      {enableSearch ? (
        <input
          className="mb-2 rounded-md border p-2"
          placeholder="Search..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      ) : null}
      <div className="max-h-80 overflow-auto">
        {showValues.map((v, i) => {
          const checked = selected.includes(v);
          return (
            <div key={v + i} className="flex items-center gap-3 py-1" onClick={() => handleChange(!checked, v)}>
              <Checkbox key={i} checked={checked} className="h-5 w-5" />
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                {v}
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function date2str(date: Date, ifNone = ""): string {
  if (!date) return ifNone;
  const month = ("0" + (date.getMonth() + 1)).slice(-2);
  const day = ("0" + date.getDate()).slice(-2);
  const year = date.getFullYear();
  return year + "-" + month + "-" + day;
}

function DateRangePopup({ user, projectId, field, value, onChange }: FilterPopupProps) {
  const { data: fieldStats } = useFieldStats(user, projectId, field?.name);
  if (field == null || value == null) return null;
  if (!fieldStats) return null;

  const handleChange = (key: keyof DateFilter, newval: Date | undefined) => {
    let result = { ...value };
    if (!newval) {
      delete result[key];
    } else result[key] = date2str(newval);
    onChange(result);
  };

  const from = value.gte ? new Date(value.gte) : undefined;
  const to = value.lte ? new Date(value.lte) : undefined;

  const fromMin = fieldStats.min == null ? undefined : new Date(fieldStats.min);
  const fromMax = to || (fieldStats.max == null ? undefined : new Date(fieldStats.max));
  const toMin = from || (fieldStats.min == null ? undefined : new Date(fieldStats.min));
  const toMax = fieldStats.max == null ? undefined : new Date(fieldStats.max);

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <DatePicker
        label={"FROM DATE"}
        value={from}
        min={fromMin}
        max={fromMax}
        onChange={(newval) => handleChange("gte", newval)}
      />
      <DatePicker
        label={"TO DATE"}
        value={to}
        min={toMin}
        max={toMax}
        onChange={(newval) => handleChange("lte", newval)}
      />
    </div>
  );
}
