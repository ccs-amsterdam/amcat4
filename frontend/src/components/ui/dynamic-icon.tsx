import {
  X,
  LineChart,
  BarChart3,
  List,
  Table2,
  Braces,
  Tag,
  CalendarDays,
  FileText,
  Link,
  Globe,
  Fingerprint,
  ToggleLeft,
  Binary,
  Tally5,
  MoveUpRight,
  Tags,
  Image,
  MonitorPlay,
  Volume2,
  Settings,
} from "lucide-react";

export function DynamicIcon({ type, className = "" }: { type: string | null; className?: string }) {
  // display types
  if (type === "line graph") return <LineChart className={className} />;
  if (type === "bar chart") return <BarChart3 className={className} />;
  if (type === "list") return <List className={className} />;
  if (type === "table") return <Table2 className={className} />;

  // field types
  if (type === "number" || type === "float" || type === "double") return <Binary className={className} />;
  if (type === "object") return <Braces className={className} />;
  if (type === "keyword") return <Tag className={className} />;
  if (type === "tag") return <Tags className={className} />;
  if (type === "date") return <CalendarDays className={className} />;
  if (type === "text") return <FileText className={className} />;
  if (type === "url") return <Link className={className} />;
  if (type === "geo") return <Globe className={className} />;
  if (type === "id") return <Fingerprint className={className} />;
  if (type === "boolean") return <ToggleLeft className={className} />;
  if (type === "integer") return <Tally5 className={className} />;
  if (type === "vector") return <MoveUpRight className={className} />;
  if (type === "image") return <Image className={className} />;
  if (type === "video") return <MonitorPlay className={className} />;
  if (type === "audio") return <Volume2 className={className} />;
  if (type === "preprocess") return <Settings className={className} />;

  if (type == null) return null;

  console.error(`Unknown icon type ${type}`);
  return <X />;
}
