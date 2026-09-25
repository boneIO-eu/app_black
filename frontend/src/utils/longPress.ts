/**
 * Intercept the next mouseup / pointerup / click at the window level
 * (capture phase, once) so it never reaches the dialog backdrop.
 *
 * Without this, @base-ui Dialog dismisses immediately because the
 * pointer-up event lands on the newly-rendered backdrop after a long press.
 *
 * Should be called right before opening a dialog from a long-press handler.
 */
export function suppressNextPointerRelease(): void {
  const stop = (e: Event) => {
    e.stopPropagation();
    e.stopImmediatePropagation();
  };
  const opts: AddEventListenerOptions = { capture: true, once: true };
  window.addEventListener('pointerup', stop, opts);
  window.addEventListener('mouseup', stop, opts);
  window.addEventListener('click', stop, opts);
  // Safety: remove listeners after 500ms in case they never fire
  setTimeout(() => {
    window.removeEventListener('pointerup', stop, opts as EventListenerOptions);
    window.removeEventListener('mouseup', stop, opts as EventListenerOptions);
    window.removeEventListener('click', stop, opts as EventListenerOptions);
  }, 500);
}

/**
 * `onContextMenu` for a tile that opens its card on long press: a right
 * click opens the same card, straight away.
 *
 * It also has to be there for touch. A long touch is how a phone asks for
 * the context menu — Chrome on Android, and any desktop browser emulating a
 * phone, raise `contextmenu` just after the 500 ms timer has opened the card,
 * and the browser's menu would land on top of it. Opening again at that
 * point is harmless: the views only record which entity the card is for.
 *
 * Text fields and links keep the browser's menu — paste and "copy link" are
 * worth more there than a card.
 */
export function openOnContextMenu(open: () => void) {
  return (e: { target: EventTarget; preventDefault: () => void }): void => {
    if ((e.target as Element).closest?.('input:not([type="checkbox"]):not([type="range"]), textarea, a[href]')) return;
    e.preventDefault();
    // The button's release comes after the card is drawn; without this it
    // lands on the backdrop and closes the card it just opened.
    suppressNextPointerRelease();
    open();
  };
}
