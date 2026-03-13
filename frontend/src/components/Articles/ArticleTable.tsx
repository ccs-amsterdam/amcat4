import { useMyProjectRole } from "@/api/project";
import { AmcatArticle, AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useEffect, useMemo, useState } from "react";

import { formatField } from "@/lib/formatField";
import { ColumnDef, SortingState } from "@tanstack/react-table";
import { DataTable } from "../ui/datatable";
import usePaginatedArticles from "./usePaginatedArticles";
import { Checkbox } from "../ui/checkbox";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
  fields: AmcatField[];
  pageSize?: number;
  children?: React.ReactNode;
  selectedIds?: string[];
  onToggleId?: (id: string) => void;
  onSetPageIds?: (ids: string[], checked: boolean) => void;
}

export default function ArticleTable({ user, projectId, query, fields, pageSize = 10, children, selectedIds, onToggleId, onSetPageIds }: Props) {
  const { role: projectRole } = useMyProjectRole(user, projectId);

  const identifierKey = useMemo(
    () => fields.filter((f) => f.identifier).map((f) => f.name).join(","),
    [fields],
  );
  const defaultSort: SortingState = useMemo(() => {
    const idFields = fields.filter((f) => f.identifier);
    return idFields.map((f) => ({ id: f.name, desc: false }));
  }, [fields]);
  const [sorting, setSorting] = useState<SortingState>(defaultSort);
  useEffect(() => { setSorting(defaultSort); }, [identifierKey]);

  const effectiveSorting = sorting.length > 0 ? sorting : defaultSort;
  const apiSort = useMemo(
    () => effectiveSorting.map((s) => ({ [s.id]: { order: s.desc ? "desc" as const : "asc" as const } })),
    [effectiveSorting],
  );

  const { articles, pageIndex, prevPage, nextPage, isFetching, pageCount } = usePaginatedArticles({
    user,
    projectId,
    query,
    fields,
    projectRole,
    pageSize,
    combineResults: true,
    sort: apiSort,
  });

  const columns: ColumnDef<AmcatArticle>[] = useMemo(() => {
    if (!fields) return [];

    const idColumn: ColumnDef<AmcatArticle> = {
      id: "_id",
      header: () => (
        <div>
          <div>ID</div>
          <div className="text-xs text-primary">identifier</div>
        </div>
      ),
      cell: ({ row }) => {
        return (
          <div className="max-w-[5rem] overflow-hidden text-ellipsis whitespace-nowrap" title={row.original._id}>
            {row.original._id}
          </div>
        );
      },
    };
    const fieldColumns: ColumnDef<AmcatArticle>[] = fields.map((field) => {
      let restricted = "";
      if (projectRole === "METAREADER" && field.metareader.access === "none") restricted = "forbidden";
      if (projectRole === "METAREADER" && field.metareader.access === "snippet") restricted = "snippet";
      return {
        id: field.name,
        header: () => (
          <div className="py-1">
            {field.name}{" "}
            <div className={`text-xs ${!!restricted ? "text-destructive" : "text-primary"}`}>
              {restricted || field.type}
            </div>
          </div>
        ),
        cell: ({ row }) => {
          return (
            <div className="min-w-[5rem] max-w-[20rem] overflow-hidden text-ellipsis whitespace-nowrap" title={String(row.original[field.name] ?? "")}>
              {formatField(row.original, field)}
            </div>
          );
        },
      };
    });

    if (selectedIds && onToggleId && onSetPageIds) {
      const pageIds = articles.map((a) => a._id);
      const allChecked = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));
      const checkboxColumn: ColumnDef<AmcatArticle> = {
        id: "__select__",
        enableSorting: false,
        header: () => (
          <Checkbox
            checked={allChecked}
            onCheckedChange={(checked) => onSetPageIds(pageIds, !!checked)}
            aria-label="Select all on page"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedIds.includes(row.original._id)}
            onCheckedChange={() => onToggleId(row.original._id)}
            aria-label="Select row"
          />
        ),
      };
      return [checkboxColumn, idColumn, ...fieldColumns];
    }

    return [idColumn, ...fieldColumns];
  }, [projectRole, fields, selectedIds, onToggleId, onSetPageIds, articles]);

  return (
    <div>
      <div className={`${true ? "flex" : "hidden"} items-center justify-end space-x-2 py-4`}>{children}</div>
      <DataTable
        data={articles}
        columns={columns}
        pagination={{ pageIndex, pageCount, nextPage, prevPage }}
        loading={isFetching}
        pageSize={pageSize}
        sorting={{ state: sorting, onChange: setSorting }}
      />
    </div>
  );
}
