import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project/articles/$articleId")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/projects/$project/dashboard",
      params: { project: params.project },
      search: { show_article_id: params.articleId },
      replace: true,
    });
  },
});
