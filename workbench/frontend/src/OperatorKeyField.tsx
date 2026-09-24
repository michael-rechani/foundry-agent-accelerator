import type { RefObject } from 'react'

export function OperatorKeyField({
  inputRef,
  disabled,
}: {
  inputRef: RefObject<HTMLInputElement | null>
  disabled: boolean
}) {
  return (
    <div className="creation-key">
      <label>
        Operator key
        <input
          type="password"
          autoComplete="off"
          ref={inputRef}
          minLength={32}
          maxLength={256}
          disabled={disabled}
        />
      </label>
      <p>
        Kept in memory for this view only, never sent to the model or saved with
        the agent.
      </p>
      <button
        className="inline-link"
        type="button"
        onClick={() => {
          if (inputRef.current) inputRef.current.value = ''
        }}
      >
        Clear operator key
      </button>
    </div>
  )
}
