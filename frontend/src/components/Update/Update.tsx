import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "../ui/card";
import { InfoBox } from "../ui/info-box";
import ActionPanel from "./ActionPanel";
import DocumentPanel from "./DocumentPanel";

interface Props {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  query: AmcatQuery;
}

export default function Update({ user, projectId, query }: Props) {
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [displayFields, setDisplayFields] = useState<AmcatField[]>([]);

  // Clear selections when the base query changes
  useEffect(() => {
    setSelectedIds([]);
  }, [query]);

  const effectiveQuery = useMemo<AmcatQuery>(() => {
    if (!selectionMode || selectedIds.length === 0) return query;
    return { filters: { _id: { values: selectedIds } } };
  }, [query, selectionMode, selectedIds]);

  const toggleId = (id: string) =>
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const setPageIds = (ids: string[], checked: boolean) =>
    setSelectedIds((prev) =>
      checked ? [...prev, ...ids.filter((id) => !prev.includes(id))] : prev.filter((id) => !ids.includes(id)),
    );

  const handleToggleSelectionMode = () => {
    setSelectionMode((m) => !m);
    setSelectedIds([]);
  };

  const handleDeleteSuccess = () => {
    setSelectedIds([]);
    setSelectionMode(false);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardContent className="pt-4">
            <ActionPanel
              user={user}
              projectId={projectId}
              query={effectiveQuery}
              onDeleteSuccess={handleDeleteSuccess}
              displayFields={displayFields}
            />
          </CardContent>
        </Card>
        <Card>
          <DocumentPanel
            user={user}
            projectId={projectId}
            query={query}
            selectionMode={selectionMode}
            onToggleSelectionMode={handleToggleSelectionMode}
            selectedIds={selectedIds}
            onToggleId={toggleId}
            onSetPageIds={setPageIds}
            onFieldsChange={setDisplayFields}
          />
        </Card>
      </div>
      <InfoBox title="Document actions" defaultOpen={false} storageKey="actionpanel-infobox">
        Use the action tabs to act on the documents matching the current query (shown in the table).
        <ul className="mt-2 list-disc pl-4 space-y-1">
          <li><strong>Update field</strong> — set a field to a new value across all matching documents.</li>
          <li><strong>Delete documents</strong> — permanently remove all matching documents.</li>
          <li><strong>Download</strong> — export matching documents as CSV, using the fields visible in the document list.</li>
        </ul>
        <p className="mt-2">By enabling the checkbox mode (
          <span className="inline-flex items-center gap-1 rounded border px-1 py-0.5 text-xs font-mono">&#9783;</span>
          ) you can select and deslect individual documents. Actions will then apply only to the selected rows instead of the entire query result.
        </p>
      </InfoBox>
    </div>
  );
}
