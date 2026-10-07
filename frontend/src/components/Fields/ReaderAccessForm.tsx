import { AmcatField, AmcatReaderAccess } from "@/interfaces";
import { ChevronDown, Eye, EyeOff, Search, SearchX } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import SimpleTooltip from "../ui/simple-tooltip";
import { Switch } from "../ui/switch";

interface Props {
  field: AmcatField;
  onChange?: (reader: AmcatReaderAccess) => void;
}

export function readerCanQuery(field: AmcatField) {
  return field.reader.queryable ?? field.reader.visible;
}

export function QueryableIcon({ queryable }: { queryable: boolean }) {
  return (
    <SimpleTooltip text={queryable ? "Can be used in queries and filters" : "Cannot be used in queries and filters"}>
      {queryable ? <Search className="h-4 w-4" /> : <SearchX className="h-4 w-4 text-destructive" />}
    </SimpleTooltip>
  );
}

/**
 * Select whether a field is queryable: by default (null) the same as whether it is visible
 */
export function QueryableRadioGroup({
  queryable,
  onChange,
  disableYes,
}: {
  queryable: boolean | null | undefined;
  onChange: (queryable: boolean | null) => void;
  disableYes?: boolean;
}) {
  const value = queryable == null ? "default" : queryable ? "yes" : "no";
  return (
    <DropdownMenuRadioGroup
      value={value}
      onValueChange={(v) => onChange(v === "default" ? null : v === "yes")}
    >
      <DropdownMenuRadioItem value="default">Same as visible</DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="yes" disabled={disableYes}>
        Yes
      </DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="no">No</DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
  );
}

export default function ReaderAccessForm({ field, onChange }: Props) {
  const reader = field.reader;

  const display = (
    <div className="flex items-center gap-2">
      {reader.visible ? <Eye /> : <EyeOff className="text-destructive" />}
      {reader.visible ? "visible" : "invisible"}
      <QueryableIcon queryable={readerCanQuery(field)} />
    </div>
  );

  if (!onChange) return display;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-2 outline-none">
        {display} <ChevronDown className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="max-w-64">
        <DropdownMenuItem
          className="flex gap-4"
          onClick={(e) => {
            e.preventDefault();
            onChange({ ...reader, visible: !reader.visible });
          }}
        >
          {reader.visible ? <Eye /> : <EyeOff className="text-destructive" />}
          <Switch checked={reader.visible} onCheckedChange={() => {}} className="scale-75" />
          visible
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Use in queries and filters</DropdownMenuLabel>
        <QueryableRadioGroup queryable={reader.queryable} onChange={(queryable) => onChange({ ...reader, queryable })} />
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Applies to users with the READER role (writers and admins can always see and query all fields).
          Metareaders can never see or query more than readers.
        </DropdownMenuLabel>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
