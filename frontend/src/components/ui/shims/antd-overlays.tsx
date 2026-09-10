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
import { Button } from "@/components/ui/shims/antd-button";
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
/**
 * The antd overlay surface these shims accept.
 *
 * Enumerated by hand for the reason this layer exists: an unrecognised prop
 * falls into `...props` and vanishes without a warning. Two of the props below
 * are here precisely because that happened — `open`/`visible` on the Popover
 * (Radix reads a bare `open` as fully controlled, so Esc and outside-click
 * could not close it) and the antd-only `trigger`/`arrow`, which leaked onto
 * the DOM and drew React warnings.
 */
type Placement =
  | "top"
  | "topLeft"
  | "topRight"
  | "bottom"
  | "bottomLeft"
  | "bottomRight"
  | "left"
  | "leftTop"
  | "leftBottom"
  | "right"
  | "rightTop"
  | "rightBottom";

/** antd's menu descriptor, as the call-sites here use it. */
/** antd's menu click payload: the key, plus the originating DOM event. */
interface MenuClickInfo {
  key?: string;
  domEvent?: React.MouseEvent<HTMLElement>;
}

interface MenuItem {
  key?: string;
  label?: React.ReactNode;
  icon?: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
  /** antd renders a separator for this instead of an item. */
  type?: "divider" | "group" | "item";
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
  /**
   * Overrides the id derived from the parent's `data-testid` (see Dropdown).
   * Worth setting when `key` is a uuid, which makes an unreadable locator.
   */
  "data-testid"?: string;
}

interface MenuProp {
  items?: MenuItem[];
  onClick?: (info: MenuClickInfo) => void;
}

interface ModalProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title" | "onClick"> {
  open?: boolean;
  /** antd's pre-v5 name for `open`; both are still in use here. */
  visible?: boolean;
  title?: React.ReactNode;
  onCancel?: () => void;
  onOk?: () => void;
  /** `null` removes the button row entirely, as antd does. */
  footer?: React.ReactNode;
  okText?: React.ReactNode;
  cancelText?: React.ReactNode;
  okButtonProps?: Record<string, unknown>;
  cancelButtonProps?: Record<string, unknown>;
  confirmLoading?: boolean;
  width?: number | string;
  centered?: boolean;
  maskClosable?: boolean;
  closable?: boolean;
  /** Remounts the body on reopen, which the Form shim relies on to re-seed. */
  destroyOnClose?: boolean;
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so destructuring
   * one out of these props is a type error without this line.
   */
  "data-testid"?: string;
}

interface TooltipProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title?: React.ReactNode;
  placement?: Placement;
  /**
   * antd's open delay, in SECONDS. Radix takes milliseconds, so it is scaled
   * below. Undeclared, it fell into `rest`, rode along to the trigger and
   * landed on the DOM — React warned about an unrecognised `mouseEnterDelay`
   * prop on every render of the agentic document-status list.
   */
  mouseEnterDelay?: number;
  /**
   * antd's close delay, also in seconds. Consumed but NOT honoured: Radix's
   * Tooltip has no close-delay prop (only `disableHoverableContent`, which is
   * a different behaviour). Declared so it cannot reach the DOM the way
   * `mouseEnterDelay` did.
   */
  mouseLeaveDelay?: number;
}

interface DropdownProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onClick"> {
  menu?: MenuProp;
  /** antd's pre-v5 API: a rendered menu element instead of a descriptor. */
  overlay?: React.ReactNode;
  trigger?: string[];
  placement?: Placement;
  disabled?: boolean;
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so destructuring
   * one out of these props is a type error without this line.
   */
  "data-testid"?: string;
}

interface DropdownButtonProps extends DropdownProps {
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  icon?: React.ReactNode;
}

interface PopconfirmProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title" | "onCancel"> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  onConfirm?: () => void;
  onCancel?: () => void;
  okText?: React.ReactNode;
  cancelText?: React.ReactNode;
  okType?: "primary" | "danger" | "default";
  disabled?: boolean;
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so destructuring
   * one out of these props is a type error without this line.
   */
  "data-testid"?: string;
}

interface PopoverProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title" | "content"> {
  content?: React.ReactNode;
  title?: React.ReactNode;
  placement?: Placement;
  open?: boolean;
  /** antd's pre-v5 name for `open`. */
  visible?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** antd's pre-v5 name for `onOpenChange`. */
  onVisibleChange?: (open: boolean) => void;
  /*
   * antd-only, consumed here rather than forwarded: Radix has no equivalent,
   * and letting them reach the DOM produced unknown-attribute warnings.
   */
  arrow?: boolean;
  overlayClassName?: string;
  overlayStyle?: React.CSSProperties;
  getPopupContainer?: (node: HTMLElement) => HTMLElement;
  destroyTooltipOnHide?: boolean;
  trigger?: string | string[];
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so destructuring
   * one out of these props is a type error without this line.
   */
  "data-testid"?: string;
}

interface CollapseItem {
  key: string;
  label?: React.ReactNode;
  children?: React.ReactNode;
}

/*
 * antd accepts a key, a list of keys, or nothing. Call-sites additionally
 * pass a boolean via `activeKey={someFlag && "1"}`, which evaluates to
 * `false` when the flag is off.
 */
type CollapseKey = string | string[] | boolean | undefined;

/*
 * `React.Children.toArray` REWRITES keys, turning `<Collapse.Panel key="1">`
 * into ".$1" — so comparing a call-site's `activeKey="1"` against the child's
 * key never matches and the panel silently stays shut. Strip the prefix back
 * off before comparing.
 */
function normalizeKey(key: React.Key | null | undefined): string {
  return String(key ?? "").replace(/^\.\$/, "");
}

/** True when `key` is listed as open by an antd activeKey/defaultActiveKey. */
function isKeyOpen(active: CollapseKey, key: React.Key | null): boolean {
  if (active === undefined || active === false || active === true) {
    // `true` is not a key either — antd would match nothing.
    return false;
  }
  const target = normalizeKey(key);
  return Array.isArray(active)
    ? active.some((k) => String(k) === target)
    : String(active) === target;
}

interface CollapseProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  items?: CollapseItem[];
  defaultActiveKey?: CollapseKey;
  /*
   * antd's CONTROLLED open state. All three call-sites use it, and several
   * write `activeKey={expandCard && "1"}`, so `false` reaches us meaning
   * "closed" — hence the `boolean` in CollapseKey rather than a bare string.
   */
  activeKey?: CollapseKey;
  onChange?: (key: string[]) => void;
  /** antd renders the caret itself; call-sites pass a render function. */
  expandIcon?: (panel: { isActive: boolean }) => React.ReactNode;
  /** Borderless variant — consumed so it cannot land on the DOM. */
  ghost?: boolean;
  size?: "small" | "middle" | "large";
  accordion?: boolean;
  bordered?: boolean;
}

/** antd's `Modal.confirm({...})` / `Modal.useModal()` config. */
interface ConfirmConfig {
  title?: React.ReactNode;
  content?: React.ReactNode;
  okText?: React.ReactNode;
  cancelText?: React.ReactNode;
  okType?: "primary" | "danger" | "default";
  onOk?: () => void | Promise<unknown>;
  onCancel?: () => void;
  centered?: boolean;
  width?: number | string;
}

const ModalBase = React.forwardRef<HTMLDivElement, ModalProps>(function Modal(
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
    "data-testid": testId,
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
            ? {
                width,
                maxWidth: `min(${typeof width === "number" ? `${width}px` : width}, calc(100vw - 2rem))`,
                ...style,
              }
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
        data-testid={testId}
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
            <Button
              onClick={onCancel}
              data-testid={testId ? `${testId}-cancel` : undefined}
              {...cancelButtonProps}
            >
              {cancelText}
            </Button>
            <Button
              type="primary"
              loading={confirmLoading}
              onClick={onOk}
              data-testid={testId ? `${testId}-ok` : undefined}
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
const Tooltip = React.forwardRef<HTMLDivElement, TooltipProps>(function Tooltip(
  {
    title,
    placement = "top",
    mouseEnterDelay,
    // Consumed only; see the note on the prop.
    mouseLeaveDelay: _mouseLeaveDelay,
    children,
    className,
    ...props
  },
  ref,
) {
  /*
   * Props that must reach the TRIGGER, not the tooltip bubble.
   *
   * A Tooltip is routinely the child of another `asChild` primitive — the
   * sidebar nests it inside a hover Popover — and Radix merges that parent's
   * props onto this component. Those props are pointer handlers meant for the
   * element under the cursor. Spreading them onto TooltipContent (as the whole
   * of `...props` used to be) put them on the bubble, where they never fire,
   * and the `!title` branch below dropped them entirely by returning children
   * raw. Either way the sidebar's Platform and HITL fly-outs never opened, with
   * no error — the same silent prop-drop this layer keeps producing.
   */
  const {
    onMouseEnter,
    onMouseLeave,
    onFocus,
    onBlur,
    onPointerDown,
    onPointerEnter,
    onPointerLeave,
    onClick,
    /*
     * Dropped, never forwarded. A parent Radix primitive sets `data-state` to
     * its OWN open/closed state, and spreading that onto the child overwrites
     * whatever the child was using it for. The API Deployments toggle is a
     * `<Switch>` inside a `<Tooltip>`: it kept `aria-checked="true"` but its
     * `data-state` became "closed", and since the Switch styles off
     * `data-state` an enabled deployment rendered as an empty grey pill.
     */
    "data-state": _parentState,
    ...rest
  } = props as React.HTMLAttributes<HTMLElement> & {
    "data-state"?: string;
  };
  /*
   * Undefined entries are stripped, not spread. `cloneElement` merges by key,
   * so an `onClick: undefined` from a parent that passes no handler OVERWRITES
   * the child's own — which is exactly how every sidebar item stopped
   * navigating: `<Space onClick={...}>` inside a titleless Tooltip had its
   * handler replaced with undefined and the click did nothing.
   */
  const triggerProps = Object.fromEntries(
    Object.entries({
      onMouseEnter,
      onMouseLeave,
      onFocus,
      onBlur,
      onPointerDown,
      onPointerEnter,
      onPointerLeave,
      onClick,
    }).filter(([, v]) => v !== undefined),
  );

  /*
   * Radix identifies an `asChild` trigger by the REF it passes down, and any
   * aria/data attributes it sets ride along in `rest`. Forwarding only the
   * pointer handlers made the sidebar fly-outs open with no anchor: Radix had
   * nothing to measure, so it positioned Platform's 236x308 panel at y=-616,
   * entirely above the viewport. It was open and correct — just off-screen.
   *
   * `rest` carries those attributes because a parent `asChild` primitive
   * merges them onto this component, so it belongs on the trigger too, not on
   * the tooltip bubble.
   */
  /*
   * Cast because the trigger element is whatever the call-site passed — a
   * Space, an Image, a button — so the concrete ref type is not knowable here.
   * `asChild` forwards it to that element regardless.
   */
  const anchorProps = {
    ...rest,
    ...triggerProps,
    // Same reason as the handlers above: a bare `ref` key would overwrite the
    // child's own ref with undefined whenever no parent supplied one.
    ...(ref ? { ref } : {}),
  } as Record<string, unknown>;

  if (!title) {
    // No tooltip to show, but the trigger props — ref included — still have to
    // land on the child rather than being discarded with the wrapper.
    return React.isValidElement(children)
      ? React.cloneElement(children as React.ReactElement, anchorProps)
      : children;
  }

  return (
    <TooltipProvider>
      <ShadcnTooltip
        {...(mouseEnterDelay != null
          ? { delayDuration: mouseEnterDelay * 1000 }
          : {})}
      >
        {/*
         * The outer primitive's ref and attributes go on the TRIGGER: they
         * identify the element it anchors to, and the bubble is not that
         * element. `ref` is deliberately not forwarded to TooltipContent here
         * for the same reason.
         */}
        {/*
         * The outer primitive's ref and attributes go on the TRIGGER: they
         * identify the element it anchors to, and the bubble is not that
         * element. `ref` is deliberately not forwarded to TooltipContent here
         * for the same reason.
         */}
        <TooltipTrigger asChild {...anchorProps}>
          {children}
        </TooltipTrigger>
        <TooltipContent
          side={
            placement.replace(/(Top|Bottom|Left|Right)$/, "") as
              | "top"
              | "bottom"
              | "left"
              | "right"
          }
          className={cn("max-w-xs break-words", className)}
        >
          {title}
        </TooltipContent>
      </ShadcnTooltip>
    </TooltipProvider>
  );
});

/* --------------------------------------------------------------- Dropdown */

/**
 * Radix's menu owns the keyboard: every printable keydown that reaches the
 * content runs its typeahead, which pulls DOM focus onto the item whose label
 * matches, and Enter/Space on an item activate it. antd's Menu did neither, so
 * antd call-sites put form fields straight into a menu entry — Prompt Studio's
 * kebab holds the postprocessing webhook URL `<Input>`. Typing in one under
 * Radix dropped characters mid-word and threw focus out of the field.
 *
 * So keystrokes that start in a text-entry control are stopped before they
 * bubble to the item (Enter/Space activation, arrow-key roving focus) or to the
 * content (typeahead). Escape and Tab are let through: dismissal listens on
 * document natively and is unaffected either way, and Tab should still leave.
 */
function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") {
    return true;
  }
  if (tag !== "INPUT") {
    return false;
  }
  // Checkboxes and radios are keyboard-activated with Space, which is also how
  // the menu activates an item; only free-text inputs need the menu muted.
  const type = (target as HTMLInputElement).type;
  return type !== "checkbox" && type !== "radio" && type !== "button";
}

function stopKeysFromFields(event: React.KeyboardEvent): void {
  if (event.key === "Escape" || event.key === "Tab") {
    return;
  }
  if (isTextEntryTarget(event.target)) {
    event.stopPropagation();
  }
}

/**
 * antd `<Dropdown menu={{ items }}>`. antd passes menu entries as data, so the
 * shim maps them onto Radix's composed children.
 */
const DropdownBase = React.forwardRef<HTMLDivElement, DropdownProps>(
  function Dropdown(
    {
      menu,
      overlay,
      trigger,
      placement,
      disabled,
      children,
      "data-testid": testId,
      ...props
    },
    ref,
  ) {
    const items = menu?.items ?? [];

    return (
      // Radix Root takes open/onOpenChange/modal only — the remaining antd props
      // are consumed above and deliberately not forwarded.
      <DropdownMenu>
        <DropdownMenuTrigger
          asChild
          disabled={disabled}
          className="ant-dropdown-trigger"
        >
          {children}
        </DropdownMenuTrigger>
        {/*
         * `data-testid` goes on the CONTENT, alongside `ref`, and NOT on the
         * trigger: the trigger is `children`, which the call-site renders and
         * can label itself, while this panel is portalled out of the tree with
         * no stable position and only library classes to select on.
         */}
        <DropdownMenuContent ref={ref} data-testid={testId} align="end">
          {overlay ??
            items.map((item, i) =>
              item?.type === "divider" ? (
                <DropdownMenuSeparator key={`div-${i}`} />
              ) : (
                <DropdownMenuItem
                  /*
                   * `p-0` plus a padded title span, rather than padding on the
                   * item itself. antd's menu entries are frequently a whole
                   * interactive element (ConfirmModal's clickable Space, for
                   * one), and Radix closes the menu on pointerdown ANYWHERE in
                   * the item — so a click in the item's own padding ring
                   * dismissed the menu without ever reaching that element.
                   * Delete therefore worked only "sometimes". Moving the
                   * padding inward keeps the same hit area but makes all of it
                   * belong to the child.
                   */
                  className="ant-dropdown-menu-item p-0"
                  key={item?.key ?? i}
                  data-testid={
                    item?.["data-testid"] ??
                    (testId && item?.key
                      ? `${testId}-item-${item.key}`
                      : undefined)
                  }
                  disabled={item?.disabled}
                  onClick={(e) => {
                    menu?.onClick?.({ key: item?.key, domEvent: e });
                    item?.onClick?.(e);
                  }}
                >
                  {/*
                   * The padding is pushed onto the DEEPEST element via
                   * `[&>*]:px-2 [&>*]:py-1.5`, not held on a wrapper. Radix
                   * closes the menu on pointerdown anywhere in the item, so any
                   * padding a label sits *inside* is a dead ring: the menu
                   * dismisses and the label's own handler never fires. That is
                   * why Delete only worked sometimes. Giving the label the
                   * padding makes the entire row its click target.
                   *
                   * The fallback padding on the span covers plain-text labels,
                   * which have no child to push it onto.
                   */}
                  {item?.icon ? (
                    <span className="flex shrink-0 items-center pl-2">
                      {item.icon}
                    </span>
                  ) : null}
                  <span
                    className={cn(
                      "ant-dropdown-menu-title-content w-full",
                      "[&>*]:w-full [&>*]:px-2 [&>*]:py-1.5",
                      // Only pads when the label is bare text, not an element.
                      "[&:not(:has(>*))]:px-2 [&:not(:has(>*))]:py-1.5",
                    )}
                    /*
                     * Held here rather than on the DropdownMenuItem: Radix
                     * composes its own keydown handler onto the item element,
                     * and stopPropagation cannot cancel a handler bound to the
                     * same node. From a descendant it stops both the item's and
                     * the content's.
                     */
                    onKeyDown={stopKeysFromFields}
                  >
                    {item?.label}
                  </span>
                </DropdownMenuItem>
              ),
            )}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  },
);

/**
 * antd `<Dropdown.Button>` — a split button: `children` is a normal action
 * button that fires `onClick`, and a separate chevron half opens the menu.
 *
 * Distinct from `<Dropdown>`, where the child IS the trigger. Rendering the
 * menu items as one grouped control keeps the two halves' hit targets apart,
 * which is the whole point of the component: clicking "Download File" must
 * download, not open a menu.
 */
const DropdownButton = React.forwardRef<HTMLDivElement, DropdownButtonProps>(
  function DropdownButton(
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
  },
);

const Dropdown = Object.assign(DropdownBase, { Button: DropdownButton });

/* ------------------------------------------------------------- Popconfirm */

/**
 * antd `<Popconfirm title description onConfirm>`. Uses AlertDialog so the
 * confirm semantics match useConfirm() rather than being a second pattern.
 */
const Popconfirm = React.forwardRef<HTMLDivElement, PopconfirmProps>(
  function Popconfirm(
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
      "data-testid": testId,
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
        {/*
         * On the CONTENT, with `ref` — `...props` lands on Radix's Root, which
         * renders no DOM, so an id written at a call-site reached nothing.
         *
         * The two buttons derive from it because they are the whole point of
         * the component and cannot be labelled from outside: the shim builds
         * them from `okText`/`cancelText`, they are portalled, and they carry
         * nothing but library classes. Confirming a delete is exactly the step
         * a test has to drive.
         */}
        <AlertDialogContent ref={ref} data-testid={testId}>
          <AlertDialogHeader>
            <AlertDialogTitle>{title}</AlertDialogTitle>
            {description ? (
              <AlertDialogDescription>{description}</AlertDialogDescription>
            ) : null}
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={onCancel}
              data-testid={testId ? `${testId}-cancel` : undefined}
            >
              {cancelText}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={onConfirm}
              data-testid={testId ? `${testId}-ok` : undefined}
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
  },
);

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
const AntPopover = React.forwardRef<HTMLDivElement, PopoverProps>(
  function AntPopover(
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
      "data-testid": testId,
      ...props
    },
    ref,
  ) {
    const controlledOpen = open ?? visible;
    const handleOpenChange = onOpenChange ?? onVisibleChange;

    /*
     * antd's `trigger="hover"` has no Radix equivalent — Radix Popover opens
     * on click only. The prop was being destructured and then ignored, so the
     * sidebar's HITL and Platform fly-out menus simply never appeared on
     * hover: a silent prop-drop, the exact failure this layer keeps producing.
     *
     * Driven here rather than with Radix's HoverCard because the call-sites
     * also CLICK these items to navigate, and swapping the primitive would
     * change that behaviour. A small close delay keeps the menu reachable
     * while the pointer travels from the trigger to the panel.
     */
    const triggers = Array.isArray(antdTrigger)
      ? antdTrigger
      : [antdTrigger ?? "click"];
    const isHover = triggers.includes("hover");

    const [hoverOpen, setHoverOpen] = React.useState(false);
    const closeTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
    const cancelClose = () => {
      if (closeTimer.current) {
        clearTimeout(closeTimer.current);
        closeTimer.current = null;
      }
    };
    React.useEffect(() => cancelClose, []);

    const hoverHandlers = isHover
      ? {
          onMouseEnter: () => {
            cancelClose();
            setHoverOpen(true);
          },
          onMouseLeave: () => {
            cancelClose();
            closeTimer.current = setTimeout(() => setHoverOpen(false), 150);
          },
        }
      : undefined;

    // An explicit `open`/`visible` still wins, so controlled call-sites are
    // unaffected by the hover tracking above.
    const isOpen = controlledOpen ?? (isHover ? hoverOpen : undefined);

    return (
      <Popover
        open={isOpen}
        // Always present, even when the call-site tracks state itself — without
        // it Radix cannot dismiss a controlled popover at all.
        onOpenChange={(next) => {
          if (isHover) {
            setHoverOpen(next);
          }
          handleOpenChange?.(next);
        }}
        {...props}
      >
        <PopoverTrigger asChild {...hoverHandlers}>
          {children}
        </PopoverTrigger>
        <PopoverContent
          ref={ref}
          /*
           * On the CONTENT, with `ref`, not on Radix's Root — the Root renders
           * no DOM at all, so a `data-testid` in `...props` vanished. The panel
           * is portalled and the trigger is `children`, which the call-site can
           * label itself, so this is the half that needs a handle.
           */
          data-testid={testId}
          // Same handlers on the panel: without them the 150ms timer fires as
          // the pointer crosses the gap and the menu closes under the cursor.
          {...hoverHandlers}
          side={
            placement.replace(/(Top|Bottom|Left|Right)$/, "") as
              | "top"
              | "bottom"
              | "left"
              | "right"
          }
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
  },
);

/**
 * antd `<Collapse items>` / `<Collapse.Panel>`.
 *
 * `activeKey` is antd's CONTROLLED open state and every call-site in the app
 * uses it: the prompt cards and notes cards toggle their body from a chevron
 * that lives in their own header row (outside this component), and the
 * LLM-profile form drives its advanced-settings panel the same way. Supporting
 * only `defaultActiveKey` left the prop to fall into `...props` and land on the
 * DOM as an unknown attribute, while every Collapsible stayed closed forever —
 * so each prompt card rendered its title bar and nothing else: no prompt text,
 * no coverage, no LLM profile, no output.
 */
const CollapseBase = React.forwardRef<HTMLDivElement, CollapseProps>(
  function Collapse(
    {
      items,
      defaultActiveKey,
      activeKey,
      onChange,
      expandIcon,
      // consumed so they cannot land on the DOM as unknown attributes
      ghost,
      size,
      accordion,
      bordered,
      className,
      children,
      ...props
    },
    ref,
  ) {
    // Controlled whenever the call-site passes activeKey at all — including
    // the `false` that `activeKey={flag && "1"}` produces when closed.
    const controlled = activeKey !== undefined;

    const renderPanel = (
      key: React.Key | null,
      header: React.ReactNode,
      body: React.ReactNode,
      showArrow: boolean,
    ) => {
      const open = isKeyOpen(controlled ? activeKey : defaultActiveKey, key);
      /*
       * A header bar is only rendered when there is something to put in it.
       * The prompt and notes cards pass no `header` — they draw their own
       * title row, with its own expand chevron, ABOVE this component — so a
       * bar here would be an empty clickable strip wedged between that row
       * and the body. (NotesCard also leaves `showArrow` at its default, so
       * keying off the arrow alone is not enough.)
       */
      const hasHeader = Boolean(header) && showArrow;
      return (
        <Collapsible
          key={key ?? undefined}
          {...(controlled ? { open } : { defaultOpen: open })}
          onOpenChange={(next) =>
            onChange?.(next && key != null ? [normalizeKey(key)] : [])
          }
        >
          {hasHeader ? (
            <CollapsibleTrigger className="ant-collapse-header flex w-full items-center justify-between py-2 text-left font-medium">
              {header}
              {expandIcon?.({ isActive: open })}
            </CollapsibleTrigger>
          ) : null}
          <CollapsibleContent className="ant-collapse-content-box">
            {body}
          </CollapsibleContent>
        </Collapsible>
      );
    };

    // Legacy children form: <Collapse><Collapse.Panel header=…>…</Collapse.Panel></Collapse>
    if (!items) {
      const panels = React.Children.toArray(children).filter(
        (
          c,
        ): c is React.ReactElement<{
          header?: React.ReactNode;
          children?: React.ReactNode;
          showArrow?: boolean;
        }> => React.isValidElement(c),
      );
      return (
        <div ref={ref} className={className} {...props}>
          {panels.map((panel, i) =>
            renderPanel(
              panel.key ?? i,
              panel.props.header,
              panel.props.children,
              panel.props.showArrow !== false,
            ),
          )}
        </div>
      );
    }
    return (
      <div ref={ref} className={className} {...props}>
        {items.map((item) =>
          renderPanel(item.key, item.label, item.children, true),
        )}
      </div>
    );
  },
);

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
type ModalKind = "confirm" | "info" | "success" | "error" | "warning";
type ModalState = (ConfirmConfig & { kind: ModalKind }) | null;

type ModalApi = {
  confirm: (cfg?: ConfirmConfig) => void;
  info: (cfg?: ConfirmConfig) => void;
  success: (cfg?: ConfirmConfig) => void;
  error: (cfg?: ConfirmConfig) => void;
  warning: (cfg?: ConfirmConfig) => void;
  destroyAll: () => void;
};

/* Explicit tuple: without it TS widens the array to a union and the
 * destructured `api` loses its methods at every call-site. */
function useModal(): [ModalApi, React.ReactElement | null] {
  const [state, setState] = React.useState<ModalState>(null);

  const api = React.useMemo(
    () => ({
      confirm: (cfg: ConfirmConfig = {}) =>
        setState({ ...cfg, kind: "confirm" }),
      info: (cfg: ConfirmConfig = {}) => setState({ ...cfg, kind: "info" }),
      success: (cfg: ConfirmConfig = {}) =>
        setState({ ...cfg, kind: "success" }),
      error: (cfg: ConfirmConfig = {}) => setState({ ...cfg, kind: "error" }),
      warning: (cfg: ConfirmConfig = {}) =>
        setState({ ...cfg, kind: "warning" }),
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

/**
 * antd's fully-imperative `Modal.confirm({ title, onOk })`, callable outside
 * React. The cloud plugins have three of these. It mounts its own root because
 * there is no component tree to render into.
 */
function confirmStatic(cfg: ConfirmConfig = {}) {
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
}

/**
 * antd `<Collapse.Panel>` — a data holder consumed by Collapse above.
 * It MUST exist: rendering `<Collapse.Panel>` when it is undefined throws
 * React error #130, which takes down the entire route rather than just this
 * component. That is what crashed Prompt Studio.
 */
function CollapsePanel({
  children,
}: {
  children?: React.ReactNode;
  /* Read off `panel.props` by Collapse above; declared so call-sites type-check. */
  header?: React.ReactNode;
  showArrow?: boolean;
}) {
  return children ?? null;
}

/*
 * Namespace objects, assembled once here. Object.assign keeps the statics in
 * the inferred type, so `<Collapse.Panel>` and `Modal.confirm(...)` type-check
 * AND the shim-completeness guard still resolves them by value — that guard is
 * what catches a missing sub-component before React error #130 takes a whole
 * route down, which is how Prompt Studio crashed.
 */
const Modal = Object.assign(ModalBase, {
  useModal,
  confirm: confirmStatic,
});

const Collapse = Object.assign(CollapseBase, { Panel: CollapsePanel });

export {
  AntPopover as Popover,
  Collapse,
  Dropdown,
  Modal,
  Popconfirm,
  Tooltip,
};
