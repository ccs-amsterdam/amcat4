import { useEffect, useState } from "react";
import Article, { ArticleProps } from "./Article";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

/**
 * Show a single article
 */
export default function ArticleModal({ user, indexId, id, query, changeArticle, link }: ArticleProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(true);
  }, [id]);
  if (!indexId || !id) return null;

  return (
    <Dialog
      open={open}
      onOpenChange={() => {
        if (changeArticle) changeArticle(null);
        setOpen(false);
      }}
    >
      <DialogContent className=" h-[90vh] w-[95vw] max-w-6xl">
        <DialogTitle className="sr-only">Article {id}</DialogTitle>
        <DialogDescription className="sr-only">Detailed view of article {id}</DialogDescription>
        <Article user={user} id={id} indexId={indexId} query={query} link={link} />
      </DialogContent>
    </Dialog>
  );
}
