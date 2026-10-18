const helpLabel = /^help me get started$/i

// True when a question is the agent's own "Help me get started" prompt. Its
// reply only describes what the agent can do, so it has no result to double-check.
export function isHelpQuestion(
  question: string,
  prompts: { label: string; text: string }[] | undefined,
) {
  const asked = question.trim()
  return (
    !!asked &&
    !!prompts?.some(
      (prompt) => helpLabel.test(prompt.label) && prompt.text.trim() === asked,
    )
  )
}
