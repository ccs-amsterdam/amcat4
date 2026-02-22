import { AmcatField, AmcatIndexId, AmcatQuery } from "@/interfaces";
import { useState } from "react";

import { useFields } from "@/api/fields";
import { Button } from "@/components/ui/button";
import { DynamicIcon } from "@/components/ui/dynamic-icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Filter } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function fieldOptions(fields: AmcatField[], query: AmcatQuery) {
  return fields
    .filter((f) => !Object.keys(query?.filters || {}).includes(f.name))
    .filter((f) => ["date", "keyword", "tag", "number"].includes(f.type));
}

interface AddFilterProps {
  children: React.ReactNode;
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  value: AmcatQuery;
  onSubmit: (value: AmcatQuery) => void;
}

export function AddFilterButton({ children, user, indexId, value, onSubmit }: AddFilterProps) {
  const [open, setOpen] = useState(false);
  const { data: fields } = useFields(user, indexId);

  function addFilter(name: string) {
    const filters = value?.filters || {};
    onSubmit({
      ...value,
      filters: { ...filters, [name]: { justAdded: true } },
    });
  }

  if (!fields) return <Filter className="text-foreground/20" />;
  const options = fieldOptions(fields, value);

  return (
    <Popover
      open={open}
      onOpenChange={() => {
        if (options.length > 0) {
          setOpen(!open);
        } else {
          setOpen(false);
        }
      }}
    >
      <PopoverTrigger>
        <div className={options.length === 0 ? "text-foreground/20" : "cursor-pointer"}>{children}</div>
      </PopoverTrigger>
      <PopoverContent>
        <div className="grid grid-cols-1 gap-1">
          {options.map((f) => (
            <Button
              variant="outline"
              className=" flex items-center justify-start gap-2 border-2"
              key={f.name}
              onClick={() => {
                setOpen(false);
                addFilter(f.name);
              }}
            >
              <DynamicIcon type={f.type} />
              <div className="flex-auto text-center">{f.name}</div>
            </Button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
