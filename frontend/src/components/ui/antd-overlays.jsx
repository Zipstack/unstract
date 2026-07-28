import { ChevronDown } from "lucide-react";
import * as React from "react";
import ReactDOM from "react-dom/client";

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
          // .ant-modal-content is targeted by existing CSS (padding, height).
          "ant-modal-content",
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
        /*
         * antd's `width` is an exact width, not a ceiling. Setting only
         * `maxWidth` left shadcn's `w-full max-w-lg` in charge: the dialog
         * stretched to whatever space it had (570px for a `width={600}`
         * modal) and drifted off-centre, because the centring transform is
         * computed against a width the modal never actually took. Pinning
         * both makes the rendered box match the number the call-site asked
         * for, and the translate then centres it exactly.
         */
        style={
          width != null
            ? { width, maxWidth: `min(${typeof width === "number" ? `${width}px` : width}, calc(100vw - 2rem))`, ...style }
            : style
        }
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
          <DialogHeader className="ant-modal-header">
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
        ) : null}
        {/*
          antd wraps modal content in `.ant-modal-body`, and this app's CSS
          caps that element's height (`max-height: 70vh; overflow-y: auto` and
          similar) so tall modals scroll internally. Without the element those
          rules match nothing: the adapter settings form grew to 1109px in an
          800px viewport, overflowing to y=-194 and putting Submit off-screen.
          The class name is kept so the existing per-modal CSS keeps working;
          the max-height here is the fallback for modals that have none.
        */}
        <div className="ant-modal-body max-h-[70vh] overflow-y-auto">
          {children}
        </div>
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
      <DropdownMenuTrigger
        asChild
        disabled={disabled}
        className="ant-dropdown-trigger"
      >
        {children}
      </DropdownMenuTrigger>
      <DropdownMenuContent ref={ref} align="end">
        {overlay ??
          items.map((item, i) =>
            item?.type === "divider" ? (
              <DropdownMenuSeparator key={`div-${i}`} />
            ) : (
              <DropdownMenuItem
                className="ant-dropdown-menu-item"
                key={item?.key ?? i}
                disabled={item?.disabled}
                onClick={(e) => {
                  menu?.onClick?.({ key: item?.key, domEvent: e });
                  item?.onClick?.(e);
                }}
              >
                {item?.icon}
                <span className="ant-dropdown-menu-title-content">
                  {item?.label}
                </span>
              </DropdownMenuItem>
            ),
          )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
});

/**
 * antd `<Dropdown.Button>` — a split button: `children` is a normal action
 * button that fires `onClick`, and a separate chevron half opens the menu.
 *
 * Distinct from `<Dropdown>`, where the child IS the trigger. Rendering the
 * menu items as one grouped control keeps the two halves' hit targets apart,
 * which is the whole point of the component: clicking "Download File" must
 * download, not open a menu.
 */
const DropdownButton = React.forwardRef(function DropdownButton(
  {
    menu,
    overlay,
    trigger,
    placement,
    disabled,
    onClick,
    icon,
    className,
    children,
    ...props
  },
  ref,
) {
  return (
    <div className={cn("inline-flex items-center", className)}>
      <Button
        disabled={disabled}
        onClick={onClick}
        className="rounded-r-none border-r-0"
      >
        {children}
      </Button>
      <Dropdown
        ref={ref}
        menu={menu}
        overlay={overlay}
        trigger={trigger}
        placement={placement}
        disabled={disabled}
        {...props}
      >
        <Button
          disabled={disabled}
          aria-label="More actions"
          className="rounded-l-none px-2"
          icon={icon ?? <ChevronDown className="size-4" aria-hidden="true" />}
        />
      </Dropdown>
    </div>
  );
});

Dropdown.Button = DropdownButton;

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

/**
 * antd `<Popover content title trigger open onOpenChange>`.
 *
 * Three antd/Radix mismatches are reconciled here, all of which the emoji
 * picker in AddCustomToolFormModal hit at once:
 *
 *   - antd call-sites pass `open` and drive it themselves from the trigger's
 *     onClick, with no `onOpenChange`. Radix reads a bare `open` as FULLY
 *     controlled, so Esc and outside-click had nowhere to report a close and
 *     the picker could only be dismissed by clicking the button again.
 *     `onOpenChange` is therefore always supplied, falling back to antd's
 *     `onOpenChange`/`onVisibleChange` when the call-site has one.
 *   - `trigger` ("click"/"hover") is antd's API and is not a Radix prop; it
 *     was landing on the DOM as an unknown attribute.
 *   - antd sizes the bubble to its content. Radix's PopoverContent is a fixed
 *     `w-72`, which clipped the emoji picker; `w-auto` plus collision padding
 *     lets it size naturally and flip when it would run off-screen.
 */
const AntPopover = React.forwardRef(function AntPopover(
  {
    content,
    title,
    placement = "top",
    trigger: antdTrigger,
    open,
    visible,
    onOpenChange,
    onVisibleChange,
    arrow,
    overlayClassName,
    overlayStyle,
    getPopupContainer,
    destroyTooltipOnHide,
    children,
    className,
    ...props
  },
  ref,
) {
  const isOpen = open ?? visible;
  const handleOpenChange = onOpenChange ?? onVisibleChange;

  return (
    <Popover
      open={isOpen}
      // Always present, even when the call-site tracks state itself — without
      // it Radix cannot dismiss a controlled popover at all.
      onOpenChange={(next) => handleOpenChange?.(next)}
      {...props}
    >
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        ref={ref}
        side={placement.replace(/(Top|Bottom|Left|Right)$/, "")}
        /*
         * antd's placement suffix names the alignment edge, and which axis it
         * refers to depends on the side: `bottomLeft` is "below, aligned to
         * the left" while `rightTop` is "to the right, aligned to the top".
         * Both are Radix's `align="start"`; Right/Bottom suffixes are "end".
         * The previous mapping only tested Top/Bottom, so the Left/Right
         * suffixes silently fell through to `center`.
         */
        align={
          /(Top|Left)$/.test(placement)
            ? "start"
            : /(Bottom|Right)$/.test(placement)
              ? "end"
              : "center"
        }
        collisionPadding={8}
        /*
         * Content-sized, like antd's bubble.
         *
         * The earlier `max-w-[min(92vw,26rem)]` (416px) was itself a clipping
         * box: the emoji picker needs ~440px once its search field and
         * category bar are counted, so its right-hand column was sliced off
         * mid-emoji.
         *
         * `--radix-popover-content-available-width` is what the popover may
         * actually occupy on the chosen side, so the bubble grows to its
         * content and only shrinks when the viewport genuinely cannot fit it.
         * Padding is left to the call-site (via `overlayClassName`), since the
         * sidebar and ConfigureDs popovers want shadcn's default `p-4` while a
         * self-chromed widget like the picker wants none.
         */
        className={cn(
          "ant-popover-inner w-auto max-w-[var(--radix-popover-content-available-width)]",
          overlayClassName,
          className,
        )}
        style={overlayStyle}
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
  // Legacy children form: <Collapse><Collapse.Panel header=…>…</Collapse.Panel></Collapse>
  if (!items) {
    const panels = React.Children.toArray(children).filter(Boolean);
    return (
      <div ref={ref} className={className} {...props}>
        {panels.map((panel, i) => {
          const { header, children: body, showArrow } = panel.props ?? {};
          return (
            <Collapsible
              key={panel.key ?? i}
              defaultOpen={
                Array.isArray(defaultActiveKey)
                  ? defaultActiveKey.includes(panel.key)
                  : defaultActiveKey === panel.key
              }
            >
              {header || showArrow !== false ? (
                <CollapsibleTrigger className="ant-collapse-header flex w-full items-center justify-between py-2 text-left font-medium">
                  {header}
                </CollapsibleTrigger>
              ) : null}
              <CollapsibleContent className="ant-collapse-content-box">
                {body}
              </CollapsibleContent>
            </Collapsible>
          );
        })}
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
          <CollapsibleTrigger className="ant-collapse-header flex w-full items-center justify-between py-2 text-left font-medium">
            {item.label}
          </CollapsibleTrigger>
          <CollapsibleContent className="ant-collapse-content-box">
            {item.children}
          </CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  );
});

/**
 * antd's imperative modal API: `Modal.useModal()` returns `[api, contextHolder]`
 * and `api.confirm({ title, content, onOk })` opens a confirm dialog.
 *
 * ConfirmModal (used by 12 components — delete buttons across prompt studio,
 * workflows, the top nav) calls this on every click. Leaving it undefined
 * throws a TypeError and takes down whichever screen the user clicked on.
 *
 * Implemented on AlertDialog so it behaves the same as useConfirm() rather
 * than becoming a second, divergent confirm pattern.
 */
function useModal() {
  const [state, setState] = React.useState(null);

  const api = React.useMemo(
    () => ({
      confirm: (cfg = {}) => setState({ ...cfg, kind: "confirm" }),
      info: (cfg = {}) => setState({ ...cfg, kind: "info" }),
      success: (cfg = {}) => setState({ ...cfg, kind: "success" }),
      error: (cfg = {}) => setState({ ...cfg, kind: "error" }),
      warning: (cfg = {}) => setState({ ...cfg, kind: "warning" }),
      destroyAll: () => setState(null),
    }),
    [],
  );

  const close = React.useCallback(() => setState(null), []);

  const contextHolder = state ? (
    <AlertDialog
      open
      onOpenChange={(open) => {
        // Escape / outside click must behave like Cancel.
        if (!open) {
          state.onCancel?.();
          close();
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state.title ?? "Are you sure?"}</AlertDialogTitle>
          {state.content ? (
            <AlertDialogDescription>{state.content}</AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          {state.kind === "confirm" ? (
            <AlertDialogCancel
              onClick={() => {
                state.onCancel?.();
                close();
              }}
            >
              {state.cancelText ?? "Cancel"}
            </AlertDialogCancel>
          ) : null}
          <AlertDialogAction
            onClick={() => {
              state.onOk?.();
              close();
            }}
            className={
              state.okType === "danger" || state.kind === "error"
                ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                : undefined
            }
          >
            {state.okText ?? "OK"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  ) : null;

  return [api, contextHolder];
}

Modal.useModal = useModal;

/**
 * antd's fully-imperative `Modal.confirm({ title, onOk })`, callable outside
 * React. The cloud plugins have three of these. It mounts its own root because
 * there is no component tree to render into.
 */
Modal.confirm = function confirmStatic(cfg = {}) {
  if (typeof document === "undefined") {
    return { destroy: () => undefined };
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);

  const cleanup = () => {
    // Defer: unmounting during React's own commit phase warns.
    setTimeout(() => {
      root.unmount();
      host.remove();
    }, 0);
  };

  function StaticConfirm() {
    const [api, holder] = useModal();
    React.useEffect(() => {
      api.confirm({
        ...cfg,
        onOk: () => {
          cfg.onOk?.();
          cleanup();
        },
        onCancel: () => {
          cfg.onCancel?.();
          cleanup();
        },
      });
    }, [api]);
    return holder;
  }

  root.render(<StaticConfirm />);
  return { destroy: cleanup };
};

/**
 * antd `<Collapse.Panel>` — a data holder consumed by Collapse above.
 * It MUST exist: rendering `<Collapse.Panel>` when it is undefined throws
 * React error #130, which takes down the entire route rather than just this
 * component. That is what crashed Prompt Studio.
 */
Collapse.Panel = function CollapsePanel({ children }) {
  return children ?? null;
};

export {
  AntPopover as Popover,
  Collapse,
  Dropdown,
  Modal,
  Popconfirm,
  Tooltip,
};
