import { AmcatField } from "@/interfaces";
import { Check, ChevronDown } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { DynamicIcon } from "../ui/dynamic-icon";

// Mirrors backend/amcat4/systemdata/typemap.py _TYPEMAP_AMCAT_TO_ES
const TYPEMAP_AMCAT_TO_ES: Record<string, string[]> = {
  text: ["text", "annotated_text", "binary", "match_only_text"],
  date: ["date"],
  boolean: ["boolean"],
  keyword: ["keyword", "constant_keyword", "wildcard"],
  number: ["double", "float", "half_float", "scaled_float"],
  integer: ["long", "integer", "byte", "short", "unsigned_long"],
  object: ["flattened"],
  vector: ["dense_vector"],
  geo_point: ["geo_point"],
  tag: ["keyword", "wildcard"],
  url: ["keyword", "wildcard", "constant_keyword"],
  image: ["keyword"],
  video: ["keyword"],
  audio: ["keyword"],
};

function getCompatibleAmcatTypes(elasticType: string): string[] {
  return Object.entries(TYPEMAP_AMCAT_TO_ES)
    .filter(([, esTypes]) => esTypes.includes(elasticType))
    .map(([amcatType]) => amcatType);
}

interface Props {
  field: AmcatField;
  onChange?: (type: string) => void;
}

export default function TypeEditForm({ field, onChange }: Props) {
  let compatibleTypes = getCompatibleAmcatTypes(field.elastic_type);
  if (field.identifier) compatibleTypes = compatibleTypes.filter((t) => t !== "tag");

  const canEdit = onChange != null && compatibleTypes.length > 1;

  const typeDisplay = (
    <div className="flex items-center gap-2">
      <DynamicIcon type={field.type} />
      <div>
        <div className="flex items-center gap-1">
          {field.type}
          {canEdit && <ChevronDown className="h-3 w-3 text-muted-foreground" />}
        </div>
        <div className="text-xs leading-3 text-primary">{field.elastic_type}</div>
      </div>
    </div>
  );

  if (!canEdit) return typeDisplay;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="outline-none">{typeDisplay}</DropdownMenuTrigger>
      <DropdownMenuContent>
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
