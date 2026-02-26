import React, { ReactElement, useMemo, useState } from "react";

import { useArticle } from "@/api/article";
import { useFields } from "@/api/fields";
import { useMyProjectRole } from "@/api/project";

import { AmcatArticle, AmcatField, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Button } from "../ui/button";
import { Loading } from "../ui/loading";

import { highlightElasticTags } from "@/lib/highlightElasticTags";
import ArticleMultimedia from "./ArticleMultimedia";
import Meta from "./Meta";
import PreprocessStatus from "./PreprocessStatus";

export interface ArticleProps {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
  /** An article id. Can also be an array of length 1 with the article id, which can trigger setOpen if the id didn't change */
  id: string;
  /** A query, used for highlighting */
  query: AmcatQuery;
  changeArticle?: (id: string | null) => void;
  link?: string;
}

export default React.memo(Article);

function Article({ user, projectId, id, query, changeArticle, link }: ArticleProps) {
  const { data: fields, isLoading: fieldsLoading } = useFields(user, projectId);
  const documentFields = useMemo(() => fields?.filter((f) => f.client_settings.inDocument), [fields]);
  const { role: projectRole } = useMyProjectRole(user, projectId);
  const { data: article, isLoading: articleLoading } = useArticle(
    user,
    projectId,
    id,
    query,
    { highlight: true },
    projectRole,
  );

  if (fieldsLoading || articleLoading) return <Loading />;
  if (!article || !documentFields) return null;

  const hasMeta = documentFields.some((f) => f.type !== "text" && f.client_settings.inDocument);
  const hasMultimedia = documentFields.some(
    (f) => ["image", "video", "audio"].includes(f.type) && f.client_settings.inDocument,
  );
  const hasPreprocess = documentFields.some((f) => f.type === "preprocess" && f.client_settings.inDocument);

  return (
    <div className="prose grid h-full max-w-none grid-cols-1 gap-6 dark:prose-invert lg:grid-cols-[1fr,0.5fr]">
      <div className="h-full overflow-auto">
        <Body article={article} fields={documentFields} metareader={projectRole === "METAREADER"} />
      </div>
      <div className="mt-6 overflow-x-hidden">
        <div className={`${hasMeta ? "" : "hidden"} h-full rounded bg-primary/10 p-3 `}>
          {/*<h2 className=" mt-0">Meta data</h2>*/}
          <Meta
            article={article}
            fields={documentFields}
            setArticle={changeArticle}
            metareader={projectRole === "METAREADER"}
          />
        </div>
        <div className={` mt-10 overflow-hidden ${hasMultimedia ? "" : "hidden"}`}>
          <h2 className="mb-0 mt-4">Multimedia</h2>
          <ArticleMultimedia user={user} projectId={projectId} article={article} fields={documentFields} />
        </div>
        <div className={` mt-10 overflow-hidden ${hasPreprocess ? "" : "hidden"}`}>
          <h2 className="mb-0 mt-4">Preprocessing status</h2>
          <PreprocessStatus article={article} fields={documentFields} />
        </div>
      </div>
    </div>
  );
}

interface BodyProps {
  article: AmcatArticle;
  fields: AmcatField[];
  metareader: boolean;
}

const Body = ({ article, fields, metareader }: BodyProps) => {
  const titleFields = fields.filter((f) => f.client_settings.isHeading);
  const textFields = fields.filter((f) => f.type === "text" && !f.client_settings.isHeading);

  return (
    <>
      <FieldLabel>
        {titleFields.map((f, i) => (
          <span key={f.name}>
            {i > 0 ? <span className="mx-1  text-primary/20"> | </span> : ""}
            {f.name.replaceAll("_", " ").toUpperCase()}
          </span>
        ))}
      </FieldLabel>
      <h2 className=" mt-0 text-foreground/70">
        {titleFields.map((f, i) => (
          <span key={f.name}>
            {i > 0 ? <span className="mx-1  text-foreground/20"> | </span> : ""}
            {highlightElasticTags(String(article[f.name] || "NA"))}
          </span>
        ))}
      </h2>
      {textFields.map((f) => {
        if (!article[f.name]) return null;

        return (
          <TextField
            key={article.id + "_" + f.name}
            article={article}
            field={f}
            metareader={metareader}
            label={textFields.length > 1}
          />
        );
      })}
    </>
  );
};

interface TextFieldProps {
  article: AmcatArticle;
  field: AmcatField;
  metareader: boolean;
  label?: boolean;
}

function TextField({ article, field, label, metareader }: TextFieldProps) {
  const content: ReactElement<any>[] = [];
  const [maxLength, setMaxLength] = useState(2400);
  const paragraphs = String(article?.[field.name])?.split("\n") || [];
  let nchars = 0;

  let paragraph_i = 0;
  for (let paragraph of paragraphs) {
    const truncated = paragraph.length > maxLength - nchars;
    if (truncated) paragraph = paragraph.slice(0, maxLength - nchars);
    const text = highlightableValue(paragraph);
    nchars += paragraph.length;
    content.push(
      <p className="mb-3 mt-0" key={paragraph_i++}>
        {text}
        {truncated ? <span className="text-primary">...</span> : null}
      </p>,
    );

    if (truncated) {
      content.push(
        <Button
          key="showmore"
          className="mb-4 w-full rounded bg-foreground/10 text-base text-primary"
          variant="ghost"
          onClick={() => setMaxLength(Infinity)}
        >
          Show full text
        </Button>,
      );
      break;
    }
  }

  function renderContent() {
    if (!metareader || field.metareader.access === "read") return <div key="content">{content}</div>;

    if (field.metareader.access === "none")
      return (
        <div key="content" className="text-secondary">
          METAREADER limitation: cannot view the <b>{field.name}</b>
        </div>
      );

    if (field.metareader.access === "snippet") {
      return (
        <div key="content">
          <div>
            <span className=" text-secondary">
              METAREADER limitation: can only view snippet of <b>{field.name}</b>:
            </span>{" "}
            {content}
          </div>
        </div>
      );
    }
  }

  return (
    <div key={field.name} className="pb-1">
      {!label ? null : <FieldLabel>{field.name.replaceAll("_", " ").toUpperCase()}</FieldLabel>}
      {renderContent()}
    </div>
  );
}

function highlightableValue(value: string) {
  return value.includes("<em>") ? highlightElasticTags(value) : value;
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div key="label" className="text  border-primary/30 pr-1 font-bold text-primary/60">
      {children}
    </div>
  );
}
