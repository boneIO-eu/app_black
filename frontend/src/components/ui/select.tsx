import * as React from "react"
import { Select as BaseSelect } from "@base-ui/react/select"
import { CheckIcon, ChevronDownIcon } from "lucide-react"

import { cn } from "@/lib/utils"

/**
 * Recursively extracts plain text from React children.
 * Used to derive a label for Base UI SelectItem from arbitrary JSX children.
 */
function extractTextFromChildren(children: React.ReactNode): string {
  if (typeof children === "string") return children
  if (typeof children === "number") return String(children)
  if (!children) return ""
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join("")
  if (React.isValidElement(children)) {
    return extractTextFromChildren((children.props as { children?: React.ReactNode }).children)
  }
  return ""
}

/**
 * Walks the React element tree and collects {value, label} pairs from SelectItem
 * elements. This runs synchronously during render so it works even before
 * Portal-wrapped SelectItems mount.
 */
function collectItemLabels(children: React.ReactNode): Record<string, string> {
  const map: Record<string, string> = {}
  function walk(node: React.ReactNode) {
    React.Children.forEach(node, (child) => {
      if (!React.isValidElement(child)) return
      const props = child.props as Record<string, unknown>
      // Detect SelectItem by checking for value prop + children (our items always have both)
      // We use displayName/type check to be precise
      if (child.type === SelectItem && props.value != null) {
        const label = extractTextFromChildren(props.children as React.ReactNode)
        if (label) map[String(props.value)] = label
      }
      // Recurse into children
      if (props.children) {
        walk(props.children as React.ReactNode)
      }
    })
  }
  walk(children)
  return map
}

interface SelectProps {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
  disabled?: boolean
  children?: React.ReactNode
}

function Select({
  value,
  defaultValue,
  onValueChange,
  open,
  defaultOpen,
  onOpenChange,
  disabled,
  children,
}: SelectProps) {
  // Scan children tree to build value→label map for SelectValue display.
  // This runs synchronously at render time, before Portal mounts items.
  const itemLabels = React.useMemo(() => collectItemLabels(children), [children])

  return (
    <SelectLabelContext.Provider value={itemLabels}>
      <BaseSelect.Root
        value={value}
        defaultValue={defaultValue}
        onValueChange={(newValue) => onValueChange?.(newValue || "")}
        open={open}
        defaultOpen={defaultOpen}
        onOpenChange={onOpenChange}
        disabled={disabled}
      >
        {children}
      </BaseSelect.Root>
    </SelectLabelContext.Provider>
  )
}

/**
 * Context providing value→label lookup for SelectValue.
 * Populated by scanning the element tree at render time.
 */
const SelectLabelContext = React.createContext<Record<string, string>>({})

function SelectGroup({
  children,
  ...props
}: React.ComponentProps<typeof BaseSelect.Group>) {
  return <BaseSelect.Group {...props}>{children}</BaseSelect.Group>
}

function SelectValue({
  placeholder,
  className,
  children: childrenProp,
  ...props
}: React.ComponentProps<typeof BaseSelect.Value>) {
  const itemLabels = React.useContext(SelectLabelContext)

  return (
    <BaseSelect.Value placeholder={placeholder} className={className} {...props}>
      {(value: string | null) => {
        // Allow consumer render prop to take precedence
        if (childrenProp != null) {
          return typeof childrenProp === "function" ? childrenProp(value) : childrenProp
        }
        if (value == null) return placeholder ?? null
        return itemLabels[value] || value
      }}
    </BaseSelect.Value>
  )
}

function SelectTrigger({
  className,
  size = "default",
  children,
  ...props
}: React.ComponentProps<typeof BaseSelect.Trigger> & {
  size?: "sm" | "default"
}) {
  return (
    <BaseSelect.Trigger
      data-size={size}
      className={cn(
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:bg-input/30 dark:hover:bg-input/50 flex w-full items-center justify-between gap-2 rounded-[var(--radius-field)] border border-(--input-border) bg-base-100 px-3 py-2 text-sm whitespace-nowrap transition-[color,box-shadow] outline-none disabled:cursor-not-allowed disabled:opacity-50 data-[size=default]:h-10 data-[size=sm]:h-8 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      {children}
      <ChevronDownIcon className="size-4 opacity-50" />
    </BaseSelect.Trigger>
  )
}

function SelectContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof BaseSelect.Popup>) {
  return (
    <BaseSelect.Portal>
      {/* Backdrop overlay visible only on mobile */}
      <BaseSelect.Backdrop 
        data-select-backdrop=""
        className="fixed inset-0 z-50 bg-black/40 hidden max-sm:block" 
      />
      <BaseSelect.Positioner
        sideOffset={4}
        alignItemWithTrigger={false}
        className="z-50 outline-none max-sm:!fixed max-sm:!inset-x-0 max-sm:!bottom-0 max-sm:!top-auto max-sm:!transform-none max-sm:!flex max-sm:!flex-col max-sm:!justify-end max-sm:!w-full"
      >
        <BaseSelect.Popup
          data-select-popup=""
          className={cn(
            "bg-base-100 text-popover-foreground overflow-x-hidden overflow-y-auto rounded-md border border-(--input-border) shadow-md",
            "max-h-[var(--available-height)] min-w-[var(--anchor-width)]",
            "max-sm:!w-full max-sm:!min-w-0 max-sm:rounded-t-2xl max-sm:rounded-b-none max-sm:border-t max-sm:border-x max-sm:border-base-300 max-sm:max-h-[75vh] max-sm:pb-8",
            className
          )}
          {...props}
        >
          {/* Visual drag handle on mobile */}
          <div className="hidden max-sm:block w-12 h-1 bg-base-300 rounded-full mx-auto my-3 shrink-0" />
          <BaseSelect.List className="p-1 outline-none max-sm:px-3">
            {children}
          </BaseSelect.List>
        </BaseSelect.Popup>
      </BaseSelect.Positioner>
    </BaseSelect.Portal>
  )
}

function SelectLabel({
  className,
  ...props
}: React.ComponentProps<typeof BaseSelect.GroupLabel>) {
  return (
    <BaseSelect.GroupLabel
      className={cn("text-muted-foreground px-2 py-1.5 text-xs", className)}
      {...props}
    />
  )
}

function SelectItem({
  className,
  children,
  label,
  ...props
}: React.ComponentProps<typeof BaseSelect.Item>) {
  const derivedLabel = label ?? extractTextFromChildren(children)

  return (
    <BaseSelect.Item
      label={derivedLabel || undefined}
      className={cn(
        "focus:bg-base-200 focus:text-accent-foreground data-[highlighted]:bg-base-200 relative flex w-full cursor-default items-center gap-2 rounded-sm py-1.5 pr-8 pl-2 text-sm outline-hidden select-none data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 max-sm:py-3 max-sm:text-base",
        className
      )}
      {...props}
    >
      <span className="absolute right-2 flex size-3.5 items-center justify-center">
        <BaseSelect.ItemIndicator>
          <CheckIcon className="size-4" />
        </BaseSelect.ItemIndicator>
      </span>
      <BaseSelect.ItemText>{children}</BaseSelect.ItemText>
    </BaseSelect.Item>
  )
}

function SelectSeparator({
  className,
  ...props
}: React.ComponentProps<typeof BaseSelect.Separator>) {
  return (
    <BaseSelect.Separator
      className={cn("bg-border pointer-events-none -mx-1 my-1 h-px", className)}
      {...props}
    />
  )
}

function SelectScrollUpButton() {
  return null
}

function SelectScrollDownButton() {
  return null
}

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
}
