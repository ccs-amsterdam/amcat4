import { useMyIndexrole } from "@/api";
import { AmcatArticle, AmcatField, AmcatIndexId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useMemo, useState } from "react";

import { formatField } from "@/lib/formatField";
import { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "../ui/datatable";
import usePaginatedArticles from "./usePaginatedArticles";

interface Props {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  query: AmcatQuery;
  fields: AmcatField[];
  children?: React.ReactNode;
}

export default function ArticleTable({ user, indexId, query, fields, children }: Props) {
  const [pageSize] = useState(6);
  const indexRole = useMyIndexrole(user, indexId);
  const { articles, pageIndex, prevPage, nextPage, isFetching, pageCount } = usePaginatedArticles({
    user,
    indexId,
    query,
    fields,
    indexRole,
    pageSize,

    combineResults: true,
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
          <div className="max-w-[5rem] overflow-hidden text-ellipsis whitespace-nowrap">
            <span title={row.original._id}>{row.original._id}</span>
          </div>
        );
      },
    };
    const columns: ColumnDef<AmcatArticle>[] = fields.map((field) => {
      let restricted = "";
      if (indexRole === "METAREADER" && field.metareader.access === "none") restricted = "forbidden";
      if (indexRole === "METAREADER" && field.metareader.access === "snippet") restricted = "snippet";
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
            <div className="line-clamp-3 max-h-20 min-w-[5rem] overflow-hidden text-ellipsis break-words">
              {formatField(row.original, field)}
            </div>
          );
        },
      };
    });
    return [idColumn, ...columns];
  }, [indexRole, fields]);

  return (
    <div>
      <div className={`${true ? "flex" : "hidden"} items-center justify-end space-x-2 py-4`}>{children}</div>
      <DataTable
        data={articles}
        columns={columns}
        pagination={{ pageIndex, pageCount, nextPage, prevPage }}
        loading={isFetching}
        pageSize={pageSize}
      />
    </div>
  );
}
