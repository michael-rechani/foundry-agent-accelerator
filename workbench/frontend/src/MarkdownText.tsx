import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function MarkdownText({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children }) => <span className="source-link">{children}</span>,
        img: ({ alt }) => <span>{alt}</span>,
        table: ({ children }) => (
          // Keyboard users need focus here to scroll a wide table sideways.
          <div
            className="table-scroll"
            role="region"
            aria-label="Table"
            // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
            tabIndex={0}
          >
            <table>{children}</table>
          </div>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  )
}
