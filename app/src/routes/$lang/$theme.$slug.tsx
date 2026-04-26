import { createFileRoute } from "@tanstack/react-router";
import { ArticlePanel } from "~/components/ArticlePanel";

export const Route = createFileRoute("/$lang/$theme/$slug")({
  component: ArticleRoute,
});

function ArticleRoute() {
  const { lang, theme, slug } = Route.useParams();
  return <ArticlePanel lang={lang} theme={theme} slug={slug} />;
}
