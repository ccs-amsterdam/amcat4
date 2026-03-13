import { useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { Button } from "./button";
import { Input } from "./input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./dropdown-menu";

interface Props {
  values: string[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  valuesLabel?: string;
  icon?: React.ReactNode;
  inputPlaceholder?: string;
}

/**
 * Select an existing value from a list, or create/type a new one.
 * When no existing values exist, shows only the input.
 */
export function ValueSelector({
  values,
  value,
  onChange,
  placeholder = "Select or create…",
  valuesLabel = "Existing values",
  icon,
  inputPlaceholder = "Enter new value…",
}: Props) {
  const [createNew, setCreateNew] = useState(false);
  const canOnlyCreate = values.length === 0;
  const showInput = createNew || canOnlyCreate;

  const selectExisting = (v: string) => {
    setCreateNew(false);
    onChange(v);
  };

  const startCreate = () => {
    setCreateNew(true);
    onChange("");
  };

  const triggerLabel = showInput ? (value || "new") : (value || placeholder);

  return (
    <div className="flex gap-3">
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={canOnlyCreate}>
          <Button className="flex w-max items-center gap-2">
            {icon}
            {triggerLabel}
            <ChevronDown className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem
            onClick={startCreate}
            className={`flex items-center gap-2 ${createNew ? "hidden" : ""}`}
          >
            <Plus />
            Create a new value
          </DropdownMenuItem>
          <DropdownMenuSeparator className={createNew ? "hidden" : ""} />
          <DropdownMenuLabel className="flex items-center gap-2">
            {icon}
            {valuesLabel}
          </DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={showInput ? undefined : value}
            onValueChange={selectExisting}
            className="max-h-52 overflow-auto"
          >
            {values.map((v) => (
              <DropdownMenuRadioItem value={v} key={v} className="ml-2">
                {v}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      {showInput && (
        <Input
          className="w-48"
          placeholder={inputPlaceholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
      )}
    </div>
  );
}
