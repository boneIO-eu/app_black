import * as React from "react"
import { Dialog as BaseDialog } from "@base-ui/react/dialog"
import { XIcon } from "lucide-react"

import { cn } from "@/lib/utils"

function Dialog({
  ...props
}: React.ComponentProps<typeof BaseDialog.Root>) {
  return <BaseDialog.Root {...props} />
}

function DialogTrigger({
  ...props
}: React.ComponentProps<typeof BaseDialog.Trigger>) {
  return <BaseDialog.Trigger {...props} />
}

function DialogPortal({
  ...props
}: React.ComponentProps<typeof BaseDialog.Portal>) {
  return <BaseDialog.Portal {...props} />
}

function DialogClose({
  ...props
}: React.ComponentProps<typeof BaseDialog.Close>) {
  return <BaseDialog.Close {...props} />
}

/**
 * Dialog backdrop / overlay.
 *
 * Uses base-ui's `data-open`, `data-starting-style` and `data-ending-style`
 * attributes for CSS-transition-based animations (see index.css).
 */
function DialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof BaseDialog.Backdrop>) {
  return (
    <BaseDialog.Backdrop
      data-dialog-backdrop
      className={cn(
        "fixed inset-0 z-50 bg-black/50",
        className
      )}
      {...props}
    />
  )
}

/**
 * Dialog popup / content.
 *
 * Responsive layout:
 *  • Mobile  (<640px): bottom sheet — slides up from the bottom, full width,
 *    rounded top corners, drag handle.
 *  • Desktop (≥640px): centered modal — zoom-in, rounded all corners.
 *
 * Animations are driven by CSS transitions on `[data-dialog-popup]`
 * targeting base-ui data attributes (see index.css).
 */
function DialogContent({
  className,
  children,
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof BaseDialog.Popup> & {
  showCloseButton?: boolean
}) {
  const touchStartY = React.useRef<number | null>(null);
  const closeRef = React.useRef<HTMLButtonElement>(null);

  return (
    <DialogPortal>
      <DialogOverlay />
      <BaseDialog.Popup
        data-dialog-popup
        className={cn(
          // Base styles
          "bg-base-100 text-base-content fixed z-50 w-full border border-base-300 shadow-xl outline-none",
          // Layout
          "grid gap-4",
          // Mobile: bottom sheet
          "bottom-0 inset-x-0 rounded-t-2xl border-b-0 px-6 pb-6 pt-3 max-h-[92vh]",
          // Desktop: centered modal
          "sm:bottom-auto sm:inset-x-auto sm:top-1/2 sm:left-1/2 sm:max-w-lg sm:rounded-lg sm:border-b sm:p-6 sm:max-h-[85vh]",
          className
        )}
        {...props}
      >
        {/* Drag handle — visible only on mobile, swipe down to close */}
        <div
          className="flex justify-center pb-1 -mt-1 sm:hidden touch-none cursor-grab active:cursor-grabbing"
          aria-hidden="true"
          onTouchStart={(e) => {
            touchStartY.current = e.touches[0].clientY;
          }}
          onTouchMove={(e) => {
            if (touchStartY.current === null) return;
            const dy = e.touches[0].clientY - touchStartY.current;
            if (dy > 30) {
              touchStartY.current = null;
              closeRef.current?.click();
            }
          }}
          onTouchEnd={() => {
            touchStartY.current = null;
          }}
        >
          <div className="h-1 w-10 rounded-full bg-base-content/20" />
        </div>
        {children}
        {/* Hidden close button for programmatic dismiss */}
        <BaseDialog.Close ref={closeRef} className="hidden" tabIndex={-1} aria-hidden="true" />
        {showCloseButton && (
          <BaseDialog.Close
            className="ring-offset-base-100 focus:ring-primary data-[open]:bg-base-200 data-[open]:text-base-content/80 absolute top-4 right-4 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 cursor-pointer"
          >
            <XIcon />
            <span className="sr-only">Close</span>
          </BaseDialog.Close>
        )}
      </BaseDialog.Popup>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("flex flex-col gap-2 text-center sm:text-left", className)}
      {...props}
    />
  )
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
        className
      )}
      {...props}
    />
  )
}

function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof BaseDialog.Title>) {
  return (
    <BaseDialog.Title
      className={cn("text-lg leading-none font-semibold", className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof BaseDialog.Description>) {
  return (
    <BaseDialog.Description
      className={cn("text-base-content/70 text-sm", className)}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
