import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function MarkdownText({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children }) => <span className="source-link">{children}</span>,
        img: ({ alt }) => <span>{alt}</span>,
      }}
    >
      {text}
    </ReactMarkdown>
  )
}
