import { AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useFields } from "@/api/fields";
import { useFieldValues } from "@/api/fieldValues";
import { useUpdateByQuery } from "@/api/updateByQuery";
import { useCount } from "@/api/aggregate";
import { useState } from "react";
import { Loading } from "../ui/loading";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
import { Switch } from "../ui/switch";
import { Label } from "../ui/label";
import { DynamicIcon } from "../ui/dynamic-icon";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { CalendarIcon, Clock2, X } from "lucide-react";
import { ValueSelector } from "../ui/value-selector";
import CodeExample from "@/components/CodeExample/CodeExample";

function TimeInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [h, m, s] = value ? value.split(":") : ["", "", ""];

  const pad = (v: string) => v.padStart(2, "0");

  const update = (part: "h" | "m" | "s", raw: string) => {
    const num = Math.max(0, Math.min(part === "h" ? 23 : 59, parseInt(raw || "0", 10)));
    const newH = part === "h" ? pad(String(num)) : (h || "00");
    const newM = part === "m" ? pad(String(num)) : (m || "00");
    const newS = part === "s" ? pad(String(num)) : (s || "00");
    onChange(`${newH}:${newM}:${newS}`);
  };

  const numInput = (part: "h" | "m" | "s", val: string, placeholder: string) => (
    <input
      type="number"
      min={0}
      max={part === "h" ? 23 : 59}
      value={val}
      placeholder={placeholder}
      onChange={(e) => update(part, e.target.value)}
      className="w-8 bg-transparent text-center text-sm outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
    />
  );

  return (
    <div className="flex items-center rounded-md border border-input bg-background px-2 py-1">
      {numInput("h", h, "HH")}
      <span className="text-muted-foreground">:</span>
      {numInput("m", m, "MM")}
      <span className="text-muted-foreground">:</span>
      {numInput("s", s, "SS")}
      <div className="ml-1 flex-1" />
      {value ? (
        <button type="button" onClick={() => onChange("")} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      ) : (
        <Clock2 className="h-4 w-4 text-muted-foreground" />
      )}
    </div>
  );
}
import DatePicker from "../QueryForm/DatePicker";
import AddOrRemoveTag from "./AddOrRemoveTag";

function formatLocalDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const UPDATABLE_TYPES = new Set(["text", "date", "boolean", "keyword", "number", "integer", "url", "tag"]);

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function UpdateField({ user, projectId, query }: Props) {
  const [selectedField, setSelectedField] = useState("");
  const { data: fields, isLoading } = useFields(user, projectId);
  if (isLoading) return <Loading />;
  if (!fields) return null;

  const updatableFields = fields.filter((f) => !f.identifier && UPDATABLE_TYPES.has(f.type));
  const selected = fields.find((f) => f.name === selectedField);

  return (
    <div className="flex flex-col gap-4">
      <Select value={selectedField} onValueChange={setSelectedField}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select a field to update" />
        </SelectTrigger>
        <SelectContent>
          {updatableFields.map((f) => (
            <SelectItem key={f.name} value={f.name}>
              <span className="flex items-center gap-2">
                <DynamicIcon type={f.type} className="h-4 w-4" />
                {f.name}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {selected?.type === "tag" && (
        <AddOrRemoveTag user={user} projectId={projectId} query={query} field={selectedField} />
      )}
      {selected && selected.type !== "tag" && (
        <NonTagUpdateForm user={user} projectId={projectId} query={query} field={selected} />
      )}
    </div>
  );
}

interface NonTagProps {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  field: AmcatField;
}

function NonTagUpdateForm({ user, projectId, query, field }: NonTagProps) {
  const [value, setValue] = useState("");
  const [dateValue, setDateValue] = useState<Date | undefined>(undefined);
  const [timeValue, setTimeValue] = useState("");
  const [boolValue, setBoolValue] = useState(false);
  const [dateOpen, setDateOpen] = useState(false);
  const { mutateAsync, isPending } = useUpdateByQuery(user, projectId);
  const { count } = useCount(user, projectId, query);
  const { data: fieldValues } = useFieldValues(
    user,
    projectId,
    field.type === "keyword" ? field.name : undefined,
  );

  const handleSubmit = async () => {
    let parsed: string | number | boolean | null;
    if (field.type === "number" || field.type === "integer") {
      parsed = value === "" ? null : Number(value);
    } else if (field.type === "boolean") {
      parsed = boolValue;
    } else if (field.type === "date") {
      parsed = dateValue ? (timeValue ? `${formatLocalDate(dateValue)}T${timeValue}` : formatLocalDate(dateValue)) : null;
    } else {
      parsed = value;
    }
    await mutateAsync({ field: field.name, value: parsed, query });
    setValue("");
    setDateValue(undefined);
    setTimeValue("");
    setBoolValue(false);
  };

  const isDisabled =
    isPending ||
    (field.type === "boolean" ? false : field.type === "date" ? !dateValue : value === "");

  const renderInput = () => {
    if (field.type === "boolean") {
      return (
        <div className="flex items-center gap-3">
          <Switch id="bool-value" checked={boolValue} onCheckedChange={setBoolValue} />
          <Label htmlFor="bool-value">{boolValue ? "true" : "false"}</Label>
        </div>
      );
    }
    if (field.type === "number" || field.type === "integer") {
      return (
        <Input
          type="number"
          placeholder={`New value for ${field.name}`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      );
    }
    if (field.type === "date") {
      const displayValue = dateValue
        ? `${formatLocalDate(dateValue)}${timeValue ? ` ${timeValue}` : ""}`
        : null;
      return (
        <Popover open={dateOpen} onOpenChange={setDateOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-start gap-2 text-left font-normal">
              <CalendarIcon className="h-4 w-4 shrink-0" />
              {displayValue ?? <span className="text-muted-foreground">Pick a date</span>}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <DatePicker
              label={field.name}
              value={dateValue}
              min={undefined}
              max={undefined}
              onChange={setDateValue}
            />
            <div className="border-t bg-card px-3 py-2">
              <Label className="mb-1 block text-xs text-muted-foreground">Time</Label>
              <TimeInput value={timeValue} onChange={setTimeValue} />
            </div>
          </PopoverContent>
        </Popover>
      );
    }
    if (field.type === "keyword") {
      return (
        <ValueSelector
          values={fieldValues ?? []}
          value={value}
          onChange={setValue}
          placeholder={`Select or type a value…`}
          valuesLabel={`Existing ${field.name} values`}
          inputPlaceholder={`New value for ${field.name}…`}
        />
      );
    }
    // text, keyword (no values), url
    return (
      <Input
        type="text"
        placeholder={`New value for ${field.name}`}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
    );
  };

  const parsedValue: string | number | boolean | null = (() => {
    if (field.type === "number" || field.type === "integer") return value === "" ? null : Number(value);
    if (field.type === "boolean") return boolValue;
    if (field.type === "date")
      return dateValue ? (timeValue ? `${formatLocalDate(dateValue)}T${timeValue}` : formatLocalDate(dateValue)) : null;
    return value || null;
  })();

  return (
    <div className="flex flex-col gap-3">
      {renderInput()}
      <div className="flex items-center gap-2">
        <Button onClick={handleSubmit} disabled={isDisabled} className="flex-1">
          Change {field.name} in {count ?? "..."} document{count === 1 ? "" : "s"}
        </Button>
        <CodeExample action="update_field" projectId={projectId} query={query} field={field.name} value={parsedValue} />
      </div>
    </div>
  );
}
