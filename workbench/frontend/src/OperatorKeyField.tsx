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
        A shared password for whoever runs this Lab. It lets you create or
        delete a real agent in Foundry, which changes the shared project and
        costs money. Ask the Lab operator for it.
      </p>
      <p>
        You need it only to create or delete. Reading, chatting and trying
        agents work without it.
      </p>
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
