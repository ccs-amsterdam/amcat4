import { AmcatArticle, AmcatField } from "@/interfaces";
import { AlertTriangle, CheckCircle, Loader } from "lucide-react";

interface Props {
  article: AmcatArticle;
  fields: AmcatField[];
}

export default function PreprocessStatus({ article, fields }: Props) {
  const preprocessStatuses = fields.filter((f) => f.type === "preprocess");
  if (!preprocessStatuses?.length) return null;

  return (
    <div className="mt-2 flex flex-col gap-3">
      {preprocessStatuses.map((field) => {
        const value = article[field.name];

        let status = <Loader className="animate-[spin_20 000ms_linear_infinite] " />;
        let error = "";
        if (value?.status) {
          if (value.status === "error") {
            error = value?.response || "Unknown error";
            status = <AlertTriangle className="text-destructive" />;
          } else {
            status = <CheckCircle className="text-check" />;
          }
        }

        return (
          <div key={field.name}>
            <div className="grid grid-cols-[2rem,1fr] gap-3">
              <span>{status}</span>
              <span>{field.name}</span>
            </div>
            <div className={error ? "text-destructive" : ""}>{error || "No error"}</div>
          </div>
        );
      })}
    </div>
  );
}
