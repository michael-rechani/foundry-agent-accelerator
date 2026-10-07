import { type RefObject, useEffect } from 'react'

// Shows a <dialog> as a modal while it is mounted and hands focus back when it
// goes. Browsers only restore focus when a dialog closes while it is still in
// the page, and React has removed it by then. If the control that opened it is
// gone too, focus goes to `fallback` instead of being lost.
export function useModalDialog(
  dialog: RefObject<HTMLDialogElement | null>,
  fallback?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    const element = dialog.current!
    const opener = document.activeElement
    element.showModal()
    return () => {
      element.close()
      const target =
        opener instanceof HTMLElement && opener.isConnected
          ? opener
          : // oxlint-disable-next-line react-hooks/exhaustive-deps -- The fallback is wanted as it is when the dialog closes, not when it opened.
            fallback?.current
      target?.focus()
    }
  }, [dialog, fallback])
}
