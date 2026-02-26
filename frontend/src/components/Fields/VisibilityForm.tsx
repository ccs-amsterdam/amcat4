import { AmcatClientSettings, AmcatField } from "@/interfaces";
import { File, Heading, LineChart, List } from "lucide-react";

import { useEffect, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { Switch } from "../ui/switch";

interface Props {
  field: AmcatField;
  client_settings: AmcatClientSettings;
  onChange: (client_settings: AmcatClientSettings) => void;
}

const IconClass = "h-5 w-5";

const canVisualizeTypes = ["number", "integer", "date", "keyword"];

export default function VisibilityForm({ field, client_settings, onChange }: Props) {
  const canVisualize = field.type !== "text";
  const [newClientSettings, setNewClientSettings] = useState(client_settings);
  useEffect(() => setNewClientSettings(client_settings), [client_settings]);

  function renderLabel() {
    return (
      <>
        <File className={`${IconClass} ${client_settings.inDocument ? "text-foreground" : "text-foreground/30"}`} />
        <List className={`${IconClass} ${client_settings.inList ? "text-foreground" : "text-foreground/30"}`} />
        <Heading className={`${IconClass} ${client_settings.isHeading ? "text-foreground" : "text-foreground/30"}`} />
        <LineChart
          className={`${IconClass} ${client_settings.inListSummary ? "text-foreground" : "text-foreground/30"} ${
            canVisualize ? "" : "opacity-0"
          }`}
        />
      </>
    );
  }
  function updateNewClientSettings(e: React.MouseEvent<HTMLDivElement>, newSettings: AmcatClientSettings) {
    e.preventDefault();
    setNewClientSettings(newSettings);
  }

  function onClose() {
    if (newClientSettings !== client_settings) onChange(newClientSettings);
  }
  return (
    <div className="flex flex-col gap-1">
      <DropdownMenu onOpenChange={(open) => !open && onClose()}>
        <DropdownMenuTrigger className="flex items-center gap-1 outline-none">{renderLabel()}</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem
            onClick={(e) =>
              updateNewClientSettings(e, { ...newClientSettings, inDocument: !newClientSettings.inDocument })
            }
            className="flex gap-4"
          >
            <File className={newClientSettings.inDocument ? "" : "text-foreground/30"} />
            <Switch checked={!!newClientSettings.inDocument} onCheckedChange={() => {}} className="scale-75" />
            show in document
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={(e) => updateNewClientSettings(e, { ...newClientSettings, inList: !newClientSettings.inList })}
            className="flex gap-4"
          >
            <List className={newClientSettings.inList ? "" : "text-foreground/30"} />
            <Switch checked={!!newClientSettings.inList} onCheckedChange={() => {}} className="scale-75" />
            show in list
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={(e) =>
              updateNewClientSettings(e, { ...newClientSettings, isHeading: !newClientSettings.isHeading })
            }
            className="flex gap-4"
          >
            <Heading className={newClientSettings.isHeading ? "" : "text-foreground/30"} />
            <Switch checked={!!newClientSettings.isHeading} onCheckedChange={() => {}} className="scale-75" />
            show as heading (title)
          </DropdownMenuItem>
          {canVisualize ? (
            <DropdownMenuItem
              onClick={(e) =>
                updateNewClientSettings(e, { ...newClientSettings, inListSummary: !newClientSettings.inListSummary })
              }
              className="flex gap-4"
            >
              <LineChart className={newClientSettings.inListSummary ? "" : "text-foreground/30"} />
              <Switch checked={!!newClientSettings.inListSummary} onCheckedChange={() => {}} className="scale-75" />
              show graph
            </DropdownMenuItem>
          ) : null}{" "}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
