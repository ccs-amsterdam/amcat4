import { AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useFields } from "@/api/fields";
import { useState, useMemo, useEffect } from "react";
import { CardContent, CardHeader } from "../ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Button } from "../ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { Check, ListChecks, SlidersHorizontal } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { cn } from "@/lib/utils";
import ArticleTable from "../Articles/ArticleTable";
import { useCount } from "@/api/aggregate";

const COMPLEX_TYPES = new Set(["object", "vector", "geo", "image", "video", "audio", "preprocess"]);

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  selectionMode: boolean;
  onToggleSelectionMode: () => void;
  selectedIds: string[];
  onToggleId: (id: string) => void;
  onSetPageIds: (ids: string[], checked: boolean) => void;
  onFieldsChange?: (fields: AmcatField[]) => void;
}

export default function DocumentPanel({
  user, projectId, query,
  selectionMode, onToggleSelectionMode, selectedIds, onToggleId, onSetPageIds, onFieldsChange,
}: Props) {
  const { data: allFields } = useFields(user, projectId);
  const { count } = useCount(user, projectId, query);
  const [fieldSelection, setFieldSelection] = useState<string[] | null>(null);
  const [fieldPickerOpen, setFieldPickerOpen] = useState(false);
  const [pageSize, setPageSize] = useState(10);
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

  const defaultFieldNames = useMemo(
    () => allFields?.filter((f) => f.client_settings?.inList).map((f) => f.name) ?? [],
    [allFields],
  );

  const activeFieldNames: string[] = fieldSelection ?? defaultFieldNames;

  const displayFields = useMemo<AmcatField[]>(() => {
    if (!allFields) return [];
    return allFields
      .filter((f) => activeFieldNames.includes(f.name))
      .map((f) => ({ ...f, client_settings: { ...f.client_settings, inList: true } }));
  }, [allFields, activeFieldNames]);

  useEffect(() => {
    onFieldsChange?.(displayFields);
  }, [displayFields, onFieldsChange]);

  const availableFields = useMemo(
    () => allFields?.filter((f) => !f.identifier && !COMPLEX_TYPES.has(f.type)) ?? [],
    [allFields],
  );

  const toggleField = (name: string) => {
    const current = fieldSelection ?? defaultFieldNames;
    setFieldSelection(
      current.includes(name) ? current.filter((n) => n !== name) : [...current, name],
    );
  };

  const isChecked = (name: string) => activeFieldNames.includes(name);

  const selectionLabel = selectionMode && selectedIds.length > 0
    ? `${selectedIds.length} selected`
    : undefined;

  return (
    <>
      <CardHeader className="flex flex-row items-center justify-between pb-2 pt-4">
        <h3 className="text-lg font-semibold">
          {selectionMode && selectedIds.length > 0
            ? `Selected ${selectedIds.length} of ${count ?? "…"} document${count === 1 ? "" : "s"}`
            : `Selected ${count ?? "…"} document${count === 1 ? "" : "s"}`}
        </h3>
        <div className="flex items-center gap-2">
          <Button
            variant={selectionMode ? "default" : "outline"}
            size="sm"
            onClick={onToggleSelectionMode}
            title={selectionMode ? "Disable row selection" : "Enable row selection"}
          >
            <ListChecks className="h-4 w-4" />
            {selectionLabel && <span className="ml-2">{selectionLabel}</span>}
          </Button>
          <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
            <SelectTrigger className="h-8 w-auto gap-1 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              {PAGE_SIZE_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>{n} rows</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Popover open={fieldPickerOpen} onOpenChange={setFieldPickerOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm">
                <SlidersHorizontal className="mr-2 h-4 w-4" />
                Fields
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-0" align="end">
              <Command>
                <CommandInput placeholder="Search fields…" />
                <CommandList>
                  <CommandEmpty>No fields found.</CommandEmpty>
                  <CommandGroup>
                    {availableFields.map((f) => {
                      const checked = isChecked(f.name);
                      return (
                        <CommandItem
                          key={f.name}
                          value={f.name}
                          onSelect={() => toggleField(f.name)}
                        >
                          <Check className={cn("mr-2 h-4 w-4 shrink-0", checked ? "opacity-100" : "opacity-0")} />
                          <span className="flex-1 truncate">{f.name}</span>
                          <span className="ml-1 text-xs text-muted-foreground">{f.type}</span>
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>
      </CardHeader>
      <CardContent>
        <ArticleTable
          user={user}
          projectId={projectId}
          query={query}
          fields={displayFields}
          pageSize={pageSize}
          selectedIds={selectionMode ? selectedIds : undefined}
          onToggleId={selectionMode ? onToggleId : undefined}
          onSetPageIds={selectionMode ? onSetPageIds : undefined}
        />
      </CardContent>
    </>
  );
}
