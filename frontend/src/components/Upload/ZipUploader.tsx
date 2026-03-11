import { AmcatField } from "@/interfaces";
import { FolderOpen, Loader } from "lucide-react";
import Papa from "papaparse";
import { Dispatch, SetStateAction, useRef, useState } from "react";
import { Button } from "../ui/button";
import { Column, jsType, prepareData } from "./Upload";

// Imported as a URL so Vite copies the file as an asset — zero runtime cost unless pdfjs is actually used.
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

interface Props {
  fields: AmcatField[];
  setData: Dispatch<SetStateAction<Record<string, jsType>[]>>;
  setColumns: Dispatch<SetStateAction<Column[]>>;
}

interface ParseProgress {
  current: number;
  total: number;
  error?: string;
}

type ParserEntry = {
  path: string;
  date: Date | null;
  getContent: () => Promise<ArrayBuffer | string>;
};

const SPREADSHEET_EXTS = new Set([".xlsx", ".xls", ".xlsm", ".ods"]);
const DOCUMENT_EXTS = new Set([".txt", ".docx", ".pdf"]);
const ALL_EXTS = ".csv,.tsv,.xlsx,.xls,.xlsm,.ods,.zip";

function getExt(path: string): string {
  return path.toLowerCase().match(/\.[^.]+$/)?.[0] ?? "";
}

async function extractText(ext: string, content: ArrayBuffer | string): Promise<string> {
  if (ext === ".txt") return content as string;

  if (ext === ".docx") {
    const { default: mammoth } = await import("mammoth");
    const result = await mammoth.extractRawText({ arrayBuffer: content as ArrayBuffer });
    return result.value;
  }

  if (ext === ".pdf") {
    const pdfjsLib = await import("pdfjs-dist");
    pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
    const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(content as ArrayBuffer) }).promise;
    const pageTexts: string[] = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      pageTexts.push(textContent.items.map((item) => ("str" in item ? item.str : "")).join(" "));
    }
    return pageTexts.join("\n\n");
  }

  return "";
}

export function ZipUploader({ fields, setData, setColumns }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<ParseProgress | null>(null);
  const [zoneHover, setZoneHover] = useState(false);

  function handleFile(file: File) {
    const ext = getExt(file.name);

    if (ext === ".csv" || ext === ".tsv") {
      Papa.parse(file, {
        skipEmptyLines: true,
        dynamicTyping: true,
        header: false,
        complete: (result) => {
          prepareData({ importedData: result.data as jsType[][], fields, setData, setColumns });
        },
      });
      return;
    }

    if (SPREADSHEET_EXTS.has(ext)) {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const XLSX = await import("xlsx");
        const buf = new Uint8Array(e.target!.result as ArrayBuffer);
        const workbook = XLSX.read(buf, { type: "array", cellDates: true });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const rawRows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, defval: null });
        const rows = rawRows.map((row) =>
          (row as unknown[]).map((cell) => (cell instanceof Date ? cell.toISOString() : cell)),
        ) as jsType[][];
        prepareData({ importedData: rows, fields, setData, setColumns });
      };
      reader.readAsArrayBuffer(file);
      return;
    }

    if (ext === ".zip") {
      handleZipFile(file);
    }
  }

  async function handleZipFile(file: File) {
    const { default: JSZip } = await import("jszip");
    const zip = await JSZip.loadAsync(file);
    const entries: ParserEntry[] = [];
    zip.forEach((path, entry) => {
      if (entry.dir) return;
      const ext = getExt(path);
      if (!DOCUMENT_EXTS.has(ext)) return;
      entries.push({
        path,
        date: entry.date ?? null,
        getContent: () => (ext === ".txt" ? entry.async("string") : entry.async("arraybuffer")),
      });
    });
    await processEntries(entries);
  }

  async function handleFolderFiles(files: FileList) {
    const entries: ParserEntry[] = [];
    for (const file of Array.from(files)) {
      const relPath = file.webkitRelativePath || file.name;
      const ext = getExt(relPath);
      if (!DOCUMENT_EXTS.has(ext)) continue;
      // Strip the top-level folder name (the selected folder itself)
      const strippedPath = relPath.split("/").slice(1).join("/") || file.name;
      entries.push({
        path: strippedPath,
        date: new Date(file.lastModified),
        getContent: () => (ext === ".txt" ? file.text() : file.arrayBuffer()),
      });
    }
    await processEntries(entries);
  }

  async function processEntries(entries: ParserEntry[]) {
    setProgress({ current: 0, total: entries.length });

    interface RawRow {
      filename: string;
      folder: string;
      text: string;
      date: string;
    }

    const rows: RawRow[] = [];

    for (let i = 0; i < entries.length; i++) {
      setProgress({ current: i + 1, total: entries.length });
      const { path, date, getContent } = entries[i];
      const ext = getExt(path);
      const parts = path.split("/");
      const filename = parts[parts.length - 1].replace(/\.[^.]+$/, "");
      const folder = parts.slice(0, -1).join("/");

      try {
        const content = await getContent();
        const text = await extractText(ext, content);
        if (!text.trim()) continue;
        rows.push({ filename, folder, text, date: date ? date.toISOString().split("T")[0] : "" });
      } catch (e) {
        console.warn(`Skipping ${path}:`, e);
      }
    }

    if (rows.length === 0) {
      setProgress({ current: 0, total: 0, error: "No text could be extracted from the files." });
      return;
    }

    // Only include folder column if at least one file has a subfolder; fill others with "."
    const hasFolders = rows.some((r) => r.folder !== "");
    if (hasFolders) rows.forEach((r) => { if (!r.folder) r.folder = "."; });

    // Only include date column if at least one file has a date
    const hasDates = rows.some((r) => r.date !== "");

    const headers = ["filename", ...(hasFolders ? ["folder"] : []), "text", ...(hasDates ? ["date"] : [])];
    const matrix: jsType[][] = [headers, ...rows.map((r) => headers.map((k) => r[k as keyof RawRow]))];

    setProgress(null);
    prepareData({ importedData: matrix, fields, setData, setColumns });
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <input
        ref={fileInputRef}
        type="file"
        accept={ALL_EXTS}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <input
        ref={folderInputRef}
        type="file"
        // @ts-expect-error webkitdirectory is non-standard
        webkitdirectory=""
        multiple
        className="hidden"
        onChange={(e) => {
          const files = e.target.files;
          if (files?.length) handleFolderFiles(files);
        }}
      />

      {progress ? (
        <div className="flex w-full items-center justify-center gap-3 rounded border border-dotted bg-primary/10 py-14">
          {progress.error ? (
            <span className="text-sm text-destructive">{progress.error}</span>
          ) : (
            <>
              <Loader className="h-5 w-5 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                Parsing {progress.current} / {progress.total} documents…
              </span>
            </>
          )}
        </div>
      ) : (
        <Button
          variant="outline"
          className={`${zoneHover ? "bg-primary/30" : ""} text-md flex h-auto w-full flex-col gap-1 border-dotted bg-primary/10 px-10 py-14 hover:bg-primary/20`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setZoneHover(true); }}
          onDragLeave={() => setZoneHover(false)}
          onDrop={(e) => {
            e.preventDefault();
            setZoneHover(false);
            const file = e.dataTransfer?.files?.[0];
            if (file) handleFile(file);
          }}
        >
          <span>Click to upload or drag and drop</span>
          <span className="text-xs text-muted-foreground">
            CSV, TSV, XLSX, ODS — or a ZIP of .txt / .docx / .pdf documents
          </span>
        </Button>
      )}

      <Button
        variant="ghost"
        size="sm"
        className="gap-1.5 text-xs text-muted-foreground"
        onClick={() => folderInputRef.current?.click()}
      >
        <FolderOpen className="h-3.5 w-3.5" />
        Or select a folder of documents
      </Button>
    </div>
  );
}
