import { AmcatField, AmcatMetareaderAccess } from "@/interfaces";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { ChevronDown, Eye, EyeOff, Scissors } from "lucide-react";
import { Input } from "../ui/input";
import { useEffect, useRef, useState } from "react";

interface Props {
  field: AmcatField;
  metareader_access: AmcatMetareaderAccess;
  onChangeAccess: (access: "none" | "snippet" | "read") => void;
  onChangeMaxSnippet: (nomatch_chars: number, max_matches: number, match_chars: number) => void;
}

const noneIcon = (
  <>
    <EyeOff className="text-destructive" />
    invisible
  </>
);
const snippetIcon = (
  <>
    <Scissors />
    snippet
  </>
);
const readIcon = (
  <>
    <Eye />
    visible
  </>
);

export default function MetareaderAccessForm({ field, metareader_access, onChangeAccess, onChangeMaxSnippet }: Props) {
  function renderAccess() {
    if (metareader_access.access === "none") return noneIcon;
    if (metareader_access.access === "snippet") return snippetIcon;
    if (metareader_access.access === "read") return readIcon;
  }

  return (
    <div className="flex flex-col gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-2 outline-none">
          {renderAccess()} <ChevronDown className="h-4 w-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => onChangeAccess("none")} className="flex gap-4">
            {noneIcon}
          </DropdownMenuItem>
          {field.type === "text" ? (
            <DropdownMenuItem onClick={() => onChangeAccess("snippet")} className="flex gap-4">
              {snippetIcon}
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem onClick={() => onChangeAccess("read")} className="flex gap-4">
            {readIcon}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <div className={`${metareader_access.access === "snippet" ? "" : "hidden"}`}>
        <MaxSnippetPopover metareader_access={metareader_access} onChangeMaxSnippet={onChangeMaxSnippet} />
      </div>
    </div>
  );
}

function MaxSnippetPopover({ metareader_access, onChangeMaxSnippet }: Omit<Props, "field" | "onChangeAccess">) {
  const [MaxSnippet, setMaxSnippet] = useState(metareader_access.max_snippet);
  const currentRef = useRef(MaxSnippet);

  useEffect(() => {
    currentRef.current = metareader_access.max_snippet;
    setMaxSnippet(metareader_access.max_snippet);
  }, [metareader_access, currentRef]);

  return (
    <Popover
      onOpenChange={(open) => {
        if (!open && currentRef.current !== MaxSnippet) {
          onChangeMaxSnippet(MaxSnippet?.nomatch_chars, MaxSnippet?.max_matches, MaxSnippet?.match_chars);
        }
      }}
    >
      <PopoverTrigger asChild className="cursor-pointer">
        <span className="text-primary">{`${MaxSnippet.nomatch_chars}, ${MaxSnippet.max_matches} x ${MaxSnippet.match_chars}`}</span>
      </PopoverTrigger>
      <PopoverContent className="w-full max-w-[90vw]">
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex items-center gap-3">
            <div className="flex-auto ">
              <h3 className="font-semibold text-foreground/50">Full-text snippet size</h3>
              <label>Cut of text after this number of characters*</label>
            </div>
            <Input
              type="number"
              min={1}
              className="w-28"
              onChange={(e) => setMaxSnippet({ ...MaxSnippet, nomatch_chars: Number(e.target.value) })}
              value={MaxSnippet?.nomatch_chars}
            />
          </div>
          <h3 className="text-md mb-0 border-t pt-4 font-semibold ">
            If a text query is used, show snippets per match
          </h3>
          <div className="flex items-center gap-3">
            <div className="flex-auto ">
              <h3 className="font-semibold text-foreground/50">Number of matches</h3>
              <label>If zero, always show the full-text snippet </label>
            </div>
            <Input
              type="number"
              min={0}
              className="w-28 text-foreground"
              onChange={(e) => setMaxSnippet({ ...MaxSnippet, max_matches: Number(e.target.value) })}
              value={MaxSnippet?.max_matches}
            />
          </div>
          <div className={`flex items-center gap-3 ${!MaxSnippet?.max_matches ? "opacity-50" : ""}`}>
            <div className="flex-auto ">
              <h3 className="font-semibold text-foreground/50">Query-match snippet size</h3>
              <label>Number of characters* around matched text</label>
            </div>
            <Input
              type="number"
              min={1}
              className="w-28"
              onChange={(e) => setMaxSnippet({ ...MaxSnippet, match_chars: Number(e.target.value) })}
              value={MaxSnippet?.match_chars}
            />
          </div>
          <div className="mt-2 italic text-foreground/70">
            * cuts of after last full word, so exact number of characters can be higher
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
