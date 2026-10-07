import { AmcatField, AmcatMetareaderAccess } from "@/interfaces";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { ChevronDown, Eye, EyeOff, Scissors } from "lucide-react";
import { Input } from "../ui/input";
import { useEffect, useRef, useState } from "react";
import { QueryableIcon, QueryableRadioGroup, readerCanQuery } from "./ReaderAccessForm";

interface Props {
  field: AmcatField;
  metareader_access: AmcatMetareaderAccess;
  onChangeAccess?: (access: "none" | "snippet" | "read") => void;
  onChangeMaxSnippet?: (nomatch_words: number, max_matches: number, words_per_match: number) => void;
  onChangeQueryable?: (queryable: boolean | null) => void;
}

export function metareaderCanQuery(metareader: AmcatMetareaderAccess) {
  return metareader.queryable ?? metareader.access !== "none";
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

export default function MetareaderAccessForm({
  field,
  metareader_access,
  onChangeAccess,
  onChangeMaxSnippet,
  onChangeQueryable,
}: Props) {
  // fields that are not visible / queryable for readers cannot be visible / queryable for metareaders
  const readerVisible = field.reader.visible;
  const readerQueryable = readerCanQuery(field);

  function renderAccess() {
    const icon = { none: noneIcon, snippet: snippetIcon, read: readIcon }[metareader_access.access];
    return (
      <>
        {icon}
        <QueryableIcon queryable={metareaderCanQuery(metareader_access)} />
      </>
    );
  }

  if (!onChangeAccess) {
    return <div className="flex items-center gap-2">{renderAccess()}</div>;
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
            <DropdownMenuItem
              disabled={!readerVisible}
              onClick={() => onChangeAccess("snippet")}
              className="flex gap-4"
            >
              {snippetIcon}
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem disabled={!readerVisible} onClick={() => onChangeAccess("read")} className="flex gap-4">
            {readIcon}
          </DropdownMenuItem>
          {!readerVisible && (
            <DropdownMenuLabel className="max-w-56 text-xs font-normal text-muted-foreground">
              This field is not visible for readers, so it cannot be visible for metareaders
            </DropdownMenuLabel>
          )}
          {onChangeQueryable && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Use in queries and filters</DropdownMenuLabel>
              <QueryableRadioGroup
                queryable={metareader_access.queryable}
                onChange={onChangeQueryable}
                disableYes={!readerQueryable}
              />
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <div className={`${metareader_access.access === "snippet" ? "" : "hidden"}`}>
        <MaxSnippetPopover metareader_access={metareader_access} onChangeMaxSnippet={onChangeMaxSnippet} />
      </div>
    </div>
  );
}

function MaxSnippetPopover({ metareader_access, onChangeMaxSnippet }: Pick<Props, "metareader_access" | "onChangeMaxSnippet">) {
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
          onChangeMaxSnippet?.(MaxSnippet?.nomatch_words, MaxSnippet?.max_matches, MaxSnippet?.words_per_match);
        }
      }}
    >
      <PopoverTrigger asChild className="cursor-pointer">
        <span className="text-primary">{`${MaxSnippet.nomatch_words}, ${MaxSnippet.max_matches} x ${MaxSnippet.words_per_match} words`}</span>
      </PopoverTrigger>
      <PopoverContent className="w-full max-w-[90vw]">
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex items-center gap-3">
            <div className="flex-auto ">
              <h3 className="font-semibold text-foreground/50">Full-text snippet size</h3>
              <label>Cut of text after this number of words</label>
            </div>
            <Input
              type="number"
              min={0}
              className="w-28"
              onChange={(e) => setMaxSnippet({ ...MaxSnippet, nomatch_words: Number(e.target.value) })}
              value={MaxSnippet?.nomatch_words}
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
              <label>Number of words around matched text</label>
            </div>
            <Input
              type="number"
              min={1}
              className="w-28"
              onChange={(e) => setMaxSnippet({ ...MaxSnippet, words_per_match: Number(e.target.value) })}
              value={MaxSnippet?.words_per_match}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
