import { DataTable, tooltipHeader } from "@/components/ui/datatable";
import {
  AmcatClientSettings,
  AmcatField,
  AmcatFieldType,
  AmcatMetareaderAccess,
  AmcatProjectId,
  AmcatReaderAccess,
  UpdateAmcatField,
} from "@/interfaces";
import CodeExample from "@/components/CodeExample/CodeExample";
import { ColumnDef } from "@tanstack/react-table";
import { Key, ListPlus, Pencil, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Input } from "../ui/input";
import MetareaderAccessForm, { metareaderCanQuery } from "./MetareaderAccessForm";
import ReaderAccessForm from "./ReaderAccessForm";
import VisibilityForm from "./VisibilityForm";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { CreateFieldNameInput } from "./CreateField";

import { Button } from "../ui/button";
import CreateField from "./CreateField";
import TypeEditForm from "./TypeEditForm";

interface Row extends AmcatField {
  fields: AmcatField[];
  onChange?: (field: UpdateAmcatField) => void;
}

const tableColumns: ColumnDef<Row>[] = [
  {
    accessorKey: "unique",
    header: tooltipHeader(
      "Unique",
      "Documents with the same values for all unique fields are considered the same document",
    ),
    cell: ({ row }) => {
      return row.original.unique ? <Key className="h-5 w-5 " /> : null;
    },
    size: 10,
  },
  {
    accessorKey: "name",
    header: "Field",
    cell: ({ row }) => {
      const field = row.original;
      function onRename(name: string) {
        field.onChange?.({ name: field.name, rename: name });
      }
      return <RenameField field={field} fields={field.fields} onRename={field.onChange ? onRename : undefined} />;
    },
  },
  {
    accessorKey: "type",
    header: "Type",

    cell: ({ row }) => {
      const field = row.original;
      function onTypeChange(type: AmcatFieldType) {
        // snippets are only possible for text fields
        const metareader =
          type !== "text" && field.metareader.access === "snippet"
            ? { ...field.metareader, access: "none" as const }
            : undefined;
        field.onChange?.({ name: field.name, type, ...(metareader ? { metareader } : {}) });
      }
      return <TypeEditForm field={field} onChange={field.onChange ? onTypeChange : undefined} />;
    },
  },

  {
    id: "Display",
    header: tooltipHeader(
      "Dashboard",
      "Set how this field is displayed in the dashboard. This does not (!!) affect data access (see METAREADER access).",
    ),
    cell: ({ row }) => {
      const field = row.original;

      function onChange(client_settings: AmcatClientSettings) {
        field.onChange?.({ name: field.name, client_settings });
      }

      return <VisibilityForm field={field} client_settings={field.client_settings} onChange={field.onChange ? onChange : undefined} />;
    },
  },
  {
    id: "Reader",
    header: tooltipHeader(
      "READER access",
      "Whether users with the READER role can see this field, and use it in queries and filters",
    ),
    cell: ({ row }) => {
      const field = row.original;

      function onChange(reader: AmcatReaderAccess) {
        // metareaders cannot see or query more than readers
        let metareader = field.metareader;
        if (!reader.visible && metareader.access !== "none") metareader = { ...metareader, access: "none" };
        const readerQueryable = reader.queryable ?? reader.visible;
        if (!readerQueryable && metareaderCanQuery(metareader)) metareader = { ...metareader, queryable: false };
        field.onChange?.({
          name: field.name,
          reader,
          ...(metareader !== field.metareader ? { metareader } : {}),
        });
      }

      return <ReaderAccessForm field={field} onChange={field.onChange ? onChange : undefined} />;
    },
  },
  {
    id: "Metareader",
    header: tooltipHeader(
      "METAREADER access",
      "Whether users with the METAREADER role can see this field (completely or as a snippet), and use it in queries and filters",
    ),
    cell: ({ row }) => {
      const field = row.original;
      const metareader_access = field.metareader;

      function onChange(metareader: AmcatMetareaderAccess) {
        field.onChange?.({ name: field.name, metareader });
      }
      function changeAccess(access: "none" | "snippet" | "read") {
        onChange({ ...metareader_access, access });
      }
      function changeMaxSnippet(nomatch_words: number, max_matches: number, words_per_match: number) {
        onChange({ ...metareader_access, max_snippet: { nomatch_words, max_matches, words_per_match } });
      }
      function changeQueryable(queryable: boolean | null) {
        onChange({ ...metareader_access, queryable });
      }

      return (
        <MetareaderAccessForm
          field={field}
          metareader_access={metareader_access}
          onChangeAccess={field.onChange ? changeAccess : undefined}
          onChangeMaxSnippet={field.onChange ? changeMaxSnippet : undefined}
          onChangeQueryable={field.onChange ? changeQueryable : undefined}
        />
      );
    },
  },
];

function RenameField({
  field,
  fields,
  onRename,
}: {
  field: AmcatField;
  fields: AmcatField[];
  onRename?: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(field.name);
  const [error, setError] = useState("");

  if (!onRename) return <span>{field.name}</span>;

  const disabled = !name || name === field.name || error !== "";

  return (
    <Popover
      open={open}
      onOpenChange={(open) => {
        if (open) setName(field.name);
        setOpen(open);
      }}
    >
      <PopoverTrigger className="group flex items-center gap-2 text-left outline-none">
        {field.name}
        <Pencil className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100" />
      </PopoverTrigger>
      <PopoverContent className="flex w-72 flex-col gap-2">
        <h4 className="text-sm font-semibold">Rename field</h4>
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (disabled) return;
            onRename(name);
            setOpen(false);
          }}
        >
          <CreateFieldNameInput
            name={name}
            setName={setName}
            setError={setError}
            fields={fields.filter((f) => f.name !== field.name)}
          />
          <Button type="submit" size="sm" disabled={disabled}>
            Rename
          </Button>
        </form>
        <span className="text-xs text-destructive">{error}</span>
      </PopoverContent>
    </Popover>
  );
}

interface Props {
  projectId: AmcatProjectId;
  fields: AmcatField[];
  mutate?: (action: "create" | "delete" | "update", fields: UpdateAmcatField[]) => void;
}

export default function FieldTable({ projectId, fields, mutate }: Props) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [debouncedGlobalFilter, setDebouncedGlobalFilter] = useState(globalFilter);

  useEffect(() => {
    const timeout = setTimeout(() => {
      setGlobalFilter(debouncedGlobalFilter);
    }, 250);
    return () => clearTimeout(timeout);
  }, [debouncedGlobalFilter]);

  const onChange = useCallback(
    (newField: UpdateAmcatField) => {
      mutate("update", [newField]);
    },
    [fields],
  );

  const onCreate = useCallback(
    (newField: UpdateAmcatField) => {
      mutate("create", [newField]);
    },
    [fields],
  );
  const data: Row[] =
    fields?.map((field) => {
      const row: Row = {
        ...field,
        fields,
        onChange: mutate ? onChange : undefined,
      };
      return row;
    }) || [];

  return (
    <div>
      <div className="flex items-center justify-between pb-4">
        <div className="flex items-center gap-1 md:gap-3">
          <h3 className="">Fields</h3>
          {mutate && (
            <CreateField projectId={projectId} fields={fields} onCreate={onCreate}>
              <Button variant="ghost" className="flex gap-2 p-4">
                <ListPlus />
                <span className="hidden sm:inline">Add field</span>
              </Button>
            </CreateField>
          )}
        </div>
        <div className="relative ml-auto flex items-center">
          <Input
            className="max-w-1/2 w-40 pl-8"
            value={debouncedGlobalFilter}
            onChange={(e) => setDebouncedGlobalFilter(e.target.value)}
          />
          <Search className="absolute left-2  h-5 w-5" />
        </div>
      </div>
      <DataTable columns={tableColumns} data={data} globalFilter={globalFilter} pageSize={50} />
      <div className="mt-3 flex justify-end">
        <CodeExample action="fields" projectId={projectId} />
      </div>
    </div>
  );
}
