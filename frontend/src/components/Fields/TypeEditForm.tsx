import { AmcatField, AmcatFieldType } from "@/interfaces";
import { Check, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { DynamicIcon } from "../ui/dynamic-icon";

// Field types that can be set on a field. Any type can be converted to another type;
// the server converts the existing values (and refuses if a value cannot be converted)
export const FIELD_TYPES: AmcatFieldType[] = [
  "text",
  "keyword",
  "tag",
  "date",
  "number",
  "integer",
  "boolean",
  "url",
  "image",
  "video",
  "audio",
  "object",
  "vector",
  "geo_point",
];

// These field types cannot be unique
export const NOT_UNIQUE_TYPES: AmcatFieldType[] = ["tag", "vector", "object"];

interface Props {
  field: AmcatField;
  onChange?: (type: AmcatFieldType) => void;
}

export default function TypeEditForm({ field, onChange }: Props) {
  let compatibleTypes = FIELD_TYPES;
  if (field.unique) compatibleTypes = compatibleTypes.filter((t) => !NOT_UNIQUE_TYPES.includes(t));

  const canEdit = onChange != null;

  const typeDisplay = (
    <div className="flex items-center gap-2">
      <DynamicIcon type={field.type} />
      <div className="flex items-center gap-1">
        {field.type}
        {canEdit && <ChevronDown className="h-3 w-3 text-muted-foreground" />}
      </div>
    </div>
  );

  if (!canEdit) return typeDisplay;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="outline-none">{typeDisplay}</DropdownMenuTrigger>
      <DropdownMenuContent className="max-h-80 overflow-auto">
        <DropdownMenuLabel className="max-w-56 text-xs font-normal text-muted-foreground">
          Existing values are converted to the new type. This fails if any value cannot be converted.
        </DropdownMenuLabel>
        {compatibleTypes.map((type) => (
          <DropdownMenuItem
            key={type}
            className="flex items-center gap-2"
            onClick={() => type !== field.type && onChange(type)}
          >
            <DynamicIcon type={type} />
            <span>{type}</span>
            {type === field.type && <Check className="ml-auto h-4 w-4" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
