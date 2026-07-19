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
