import ReactMarkdown from "react-markdown";
import { memo } from "react";
import remarkGfm from "remark-gfm";

const MarkdownRenderer = memo(({ content }: { content: string }) => {
  const parsedContent = content.replace(/\\n/g, '\n'); // Parse the escape sequences to convert \n to actual linebreaks
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{parsedContent}</ReactMarkdown>;
});

export default MarkdownRenderer;
