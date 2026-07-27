import * as React from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/antd-button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip as ShadcnTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * antd-compatible overlay components (P2-02..P2-05): Modal, Tooltip, Dropdown,
 * Popconfirm, Popover, Collapse.
 *
 * Shim tier per docs/shim-convention.md — these carry behaviour Radix does not
 * express the same way:
 *   - Modal: `open`/`visible` twin props, `footer={null}` to suppress the
 *     default OK/Cancel pair, `destroyOnClose` remount semantics, `width`,
 *     `centered`, `maskClosable`.
 *   - Dropdown: antd takes a `menu={{ items }}` data structure; Radix wants
 *     composed children.
 *   - Popconfirm: an inline confirm bubble, routed onto AlertDialog so its
 *     behaviour matches useConfirm().
 */

/* ------------------------------------------------------------------ Modal */

/**
 * antd `<Modal>`. `open` and the legacy `visible` alias both work.
 *
 * antd renders an OK/Cancel footer unless `footer={null}`; that default is
 * reproduced here so call-sites relying on it keep their buttons.
 */
const Modal = React.forwardRef(function Modal(
  {
    open,
    visible,
    title,
    onCancel,
    onOk,
    footer,
    okText = "OK",
    cancelText = "Cancel",
    okButtonProps,
    cancelButtonProps,
    confirmLoading,
    width,
    // consumed so it cannot land on the DOM; see the note below
    centered,
    maskClosable = true,
    closable = true,
    destroyOnClose,
    className,
    style,
    children,
    ...props
  },
  ref,
) {
  const isOpen = open ?? visible ?? false;

  // antd unmounts the body on close when destroyOnClose is set; Radix keeps
  // it mounted. Returning null reproduces the remount.
  if (destroyOnClose && !isOpen) {
    return null;
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(next) => {
        if (!next) {
          onCancel?.();
        }
      }}
    >
      <DialogContent
        ref={ref}
        className={cn(
          // NOTE: no `centered` handling here. shadcn's DialogContent is
          // ALREADY centred (`top-[50%] translate-y-[-50%]`), and adding an
          // equivalent-but-differently-spelled utility makes tailwind-merge
          // treat the two as conflicting — it drops one, leaving the dialog
          // with `transform: none` pinned to the top of the viewport with its
          // header clipped. antd's `centered` is therefore a no-op for us.
          // This shadcn DialogContent always renders its close button, so
          // antd's `closable={false}` is honoured by hiding it rather than by
          // a prop.
          !closable && "[&>button[type='button']:last-of-type]:hidden",
          className,
        )}
        style={{ maxWidth: width ?? undefined, ...style }}
        onPointerDownOutside={(e) => {
          if (!maskClosable) {
            e.preventDefault();
          }
        }}
        onEscapeKeyDown={(e) => {
          if (!maskClosable && !closable) {
            e.preventDefault();
          }
        }}
        {...props}
      >
        {title ? (
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
        ) : null}
        {children}
        {footer === null ? null : footer !== undefined ? (
          <DialogFooter>{footer}</DialogFooter>
        ) : (
          <DialogFooter>
            <Button onClick={onCancel} {...cancelButtonProps}>
              {cancelText}
            </Button>
            <Button
              type="primary"
              loading={confirmLoading}
              onClick={onOk}
              {...okButtonProps}
            >
              {okText}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
});

/* ---------------------------------------------------------------- Tooltip */

/** antd `<Tooltip title placement>`. Renders nothing extra when title is empty. */
const Tooltip = React.forwardRef(function Tooltip(
  { title, placement = "top", children, className, ...props },
  ref,
) {
  if (!title) {
    return children;
  }
  return (
    <TooltipProvider>
      <ShadcnTooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent
          ref={ref}
          side={placement.replace(/(Top|Bottom|Left|Right)$/, "")}
          className={cn("max-w-xs break-words", className)}
          {...props}
        >
          {title}
        </TooltipContent>
      </ShadcnTooltip>
    </TooltipProvider>
  );
});

/* --------------------------------------------------------------- Dropdown */

/**
 * antd `<Dropdown menu={{ items }}>`. antd passes menu entries as data, so the
 * shim maps them onto Radix's composed children.
 */
const Dropdown = React.forwardRef(function Dropdown(
  { menu, overlay, trigger, placement, disabled, children, ...props },
  ref,
) {
  const items = menu?.items ?? [];

  return (
    <DropdownMenu {...props}>
      <DropdownMenuTrigger asChild disabled={disabled}>
        {children}
      </DropdownMenuTrigger>
      <DropdownMenuContent ref={ref} align="end">
        {overlay ??
          items.map((item, i) =>
            item?.type === "divider" ? (
              <DropdownMenuSeparator key={`div-${i}`} />
            ) : (
              <DropdownMenuItem
                key={item?.key ?? i}
                disabled={item?.disabled}
                onClick={(e) => {
                  menu?.onClick?.({ key: item?.key, domEvent: e });
                  item?.onClick?.(e);
                }}
              >
                {item?.icon}
                {item?.label}
              </DropdownMenuItem>
            ),
          )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
});

/* ------------------------------------------------------------- Popconfirm */

/**
 * antd `<Popconfirm title description onConfirm>`. Uses AlertDialog so the
 * confirm semantics match useConfirm() rather than being a second pattern.
 */
const Popconfirm = React.forwardRef(function Popconfirm(
  {
    title,
    description,
    onConfirm,
    onCancel,
    okText = "OK",
    cancelText = "Cancel",
    okType,
    disabled,
    children,
    ...props
  },
  ref,
) {
  if (disabled) {
    return children;
  }

  return (
    <AlertDialog {...props}>
      <AlertDialogTrigger asChild>{children}</AlertDialogTrigger>
      <AlertDialogContent ref={ref}>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description ? (
            <AlertDialogDescription>{description}</AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>{cancelText}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className={
              okType === "danger"
                ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                : undefined
            }
          >
            {okText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
});

/* ------------------------------------------------- Popover / Collapse */

/** antd `<Popover content title trigger>`. */
const AntPopover = React.forwardRef(function AntPopover(
  { content, title, placement = "top", children, className, ...props },
  ref,
) {
  return (
    <Popover {...props}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        ref={ref}
        side={placement.replace(/(Top|Bottom|Left|Right)$/, "")}
        className={cn(className)}
      >
        {title ? <div className="mb-1 font-semibold">{title}</div> : null}
        {content}
      </PopoverContent>
    </Popover>
  );
});

/** antd `<Collapse items>` / `<Collapse.Panel>`. */
const Collapse = React.forwardRef(function Collapse(
  { items, defaultActiveKey, className, children, ...props },
  ref,
) {
  if (!items) {
    return (
      <div ref={ref} className={className} {...props}>
        {children}
      </div>
    );
  }
  return (
    <div ref={ref} className={className} {...props}>
      {items.map((item) => (
        <Collapsible
          key={item.key}
          defaultOpen={
            Array.isArray(defaultActiveKey)
              ? defaultActiveKey.includes(item.key)
              : defaultActiveKey === item.key
          }
        >
          <CollapsibleTrigger className="flex w-full items-center justify-between py-2 text-left font-medium">
            {item.label}
          </CollapsibleTrigger>
          <CollapsibleContent>{item.children}</CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  );
});

export {
  AntPopover as Popover,
  Collapse,
  Dropdown,
  Modal,
  Popconfirm,
  Tooltip,
};
