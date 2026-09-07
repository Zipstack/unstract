import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleX,
  LoaderCircle,
  Paperclip,
  Upload as UploadIcon,
  X,
} from "lucide-react";
import * as React from "react";
import { DataTable } from "@/components/data-table/DataTable";
import {
  CardContent,
  CardHeader,
  CardTitle,
  Card as ShadcnCard,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/shims/antd-button";
import { Empty } from "@/components/ui/shims/antd-leaves";
import { Skeleton as ShadcnSkeleton } from "@/components/ui/skeleton";
import {
  Tabs as ShadcnTabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

/**
 * antd-compatible structural components (P4): Table, Card, Tabs, List, Layout,
 * Upload, Result, Drawer, Menu, Segmented, Pagination, Steps, Tree, Skeleton.
 *
 * `Table` delegates to the shared DataTable (D5/D9) so there is exactly one
 * table implementation. The rest are thin wrappers that keep antd's prop names
 * so the last 68 call-site files convert by import.
 */

/** antd `<Table>` → the shared DataTable. */
/*
 * Namespace objects use Object.assign so the statics stay in the inferred
 * type: `<Card.Meta>` and `<Collapse.Panel>`-style sub-components must both
 * type-check AND remain resolvable by value, because the shim-completeness
 * guard reads them that way to catch a missing one before React error #130
 * takes down a whole route.
 */
function Column() {
  return null;
}
const Table = Object.assign(DataTable, { Column });

/** antd `<Card title extra bordered>`. */
/**
 * The antd surface these structural shims accept.
 *
 * Enumerated by hand, like the other shims, because the failure mode of this
 * layer is the silent prop-drop: a call-site passes something the shim never
 * destructures and `...props` swallows it with no error at all. `Upload.Dragger`
 * is the cautionary tale here — it was aliased to `Upload`, so the drop zone
 * rendered as a plain button and drag-and-drop simply did nothing.
 */
type SizeToken = "small" | "middle" | "large" | "default";

/** A `{ key, label }` descriptor, antd's usual shape for list-like data. */
interface KeyedItem {
  key?: string;
  label?: React.ReactNode;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  disabled?: boolean;
  /**
   * Overrides the id Tabs derives from its own `data-testid`. Worth setting
   * where `key` is a uuid or a bare ordinal, which makes a poor locator.
   */
  "data-testid"?: string;
}

interface CardProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title?: React.ReactNode;
  /** Rendered at the top-right of the header. */
  extra?: React.ReactNode;
  bordered?: boolean;
  size?: SizeToken;
  /**
   * antd's `hoverable`: the card is a click target, so it gets a pointer
   * cursor and lifts on hover. Ten call sites pass it, and until it was
   * declared here `...props` put it on the `<div>` as an unknown attribute --
   * the cards read as inert.
   */
  hoverable?: boolean;
  /** antd v5 per-slot style overrides, e.g. `{ body: {...} }`. */
  styles?: { header?: React.CSSProperties; body?: React.CSSProperties };
}

interface TabsProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  items?: Array<KeyedItem & { children?: React.ReactNode }>;
  activeKey?: string;
  defaultActiveKey?: string;
  onChange?: (key: string) => void;
  tabBarExtraContent?: React.ReactNode;
  type?: "line" | "card" | "editable-card";
  /*
   * Passed by the cloud manual-review plugin (`<Tabs … size="large">`) and
   * accepted rather than forwarded — the tab sizing comes from the shadcn
   * primitive's own classes. Declared because omitting it would make the
   * cloud build fail to compile against this interface, which is precisely
   * the silent gap that typing this layer is meant to expose.
   */
  size?: SizeToken;
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so destructuring
   * one out of these props is a type error without this line.
   */
  "data-testid"?: string;
}

interface ListProps<T = unknown> extends React.HTMLAttributes<HTMLDivElement> {
  dataSource?: T[];
  renderItem?: (item: T, index: number) => React.ReactNode;
  header?: React.ReactNode;
  footer?: React.ReactNode;
  /** antd's responsive grid; `column` picks the fixed column count. */
  grid?: { column?: number; gutter?: number };
  locale?: { emptyText?: React.ReactNode };
}

interface LayoutProps extends React.HTMLAttributes<HTMLDivElement> {
  /** antd uses this to switch the flex direction when a Sider is present. */
  hasSider?: boolean;
}

/** antd's file wrapper. `originFileObj` is the real File the call-sites read. */
interface UploadFile {
  uid?: string;
  name?: string;
  status?: "uploading" | "done" | "error" | "removed";
  originFileObj?: File;
  response?: unknown;
}

interface UploadProps
  extends Omit<React.HTMLAttributes<HTMLElement>, "onChange"> {
  /** Returning false cancels the upload, as antd does. */
  beforeUpload?: (file: File, fileList: File[]) => boolean | Promise<unknown>;
  customRequest?: (options: {
    file: File;
    onSuccess?: (body?: unknown) => void;
    onError?: (err?: unknown) => void;
  }) => void;
  onChange?: (info: { file: UploadFile; fileList: UploadFile[] }) => void;
  /**
   * antd's declarative uploader: with `action` set and no `customRequest`,
   * antd itself POSTs the file as multipart. Destructured rather than left to
   * `...props` for two reasons — the shim has to actually send the request,
   * and React rejects `action` on a non-`<form>` DOM node.
   */
  action?: string;
  headers?: Record<string, string>;
  /** The multipart field name antd posts the file under. */
  name?: string;
  accept?: string;
  multiple?: boolean;
  showUploadList?: boolean;
  fileList?: UploadFile[];
  /** antd truncates the list to this; `1` REPLACES rather than truncates. */
  maxCount?: number;
  /** Returning false (or rejecting) vetoes the removal, as antd does. */
  onRemove?: (file: UploadFile) => boolean | void | Promise<unknown>;
  disabled?: boolean;
}

interface ResultProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  status?: "success" | "error" | "info" | "warning" | "404" | "403" | "500";
  title?: React.ReactNode;
  subTitle?: React.ReactNode;
  extra?: React.ReactNode;
  icon?: React.ReactNode;
}

interface DrawerProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  open?: boolean;
  onClose?: () => void;
  title?: React.ReactNode;
  placement?: "top" | "right" | "bottom" | "left";
  width?: number | string;
  /** antd renders a top-right close button unless this is false. */
  closable?: boolean;
  /**
   * antd's per-slot style overrides. Only `body` is honoured — no call-site
   * uses the others, and silently accepting them would be worse than the
   * type error.
   */
  styles?: { body?: React.CSSProperties };
  /**
   * Accepted and ignored: Radix already unmounts the panel on close, which is
   * what antd's `destroyOnClose` asks for. Declared so it is consumed rather
   * than spread onto the DOM node.
   */
  destroyOnClose?: boolean;
}

interface SegmentedOption {
  label?: React.ReactNode;
  value: string | number;
  icon?: React.ReactNode;
}

interface SegmentedProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  /** antd accepts bare strings as well as `{ label, value }` objects. */
  options?: Array<SegmentedOption | string>;
  value?: string | number;
  onChange?: (value: string | number) => void;
  /**
   * Declared explicitly: React's `HTMLAttributes` does not carry `data-*` at
   * all — JSX lets them through on intrinsic elements only — so destructuring
   * one out of these props is a type error without this line.
   */
  "data-testid"?: string;
}

interface MenuProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onClick" | "onSelect"> {
  items?: KeyedItem[];
  selectedKeys?: string[];
  onClick?: (info: { key: string }) => void;
  /**
   * antd fires `onSelect` alongside `onClick` whenever a selectable item is
   * picked, and plenty of call sites listen on that one alone — the Output
   * Analyzer's Document List does. Without it declared here the prop fell
   * through to the <nav> as React's DOM `select` handler, which never fires
   * on a click, so switching documents silently did nothing.
   */
  onSelect?: (info: {
    key: string;
    keyPath: string[];
    selectedKeys: string[];
  }) => void;
  mode?: "vertical" | "horizontal" | "inline";
}

interface SkeletonProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  active?: boolean;
  /** `true`, or `{ rows }` for an explicit line count. */
  paragraph?: boolean | { rows?: number };
  title?: boolean;
}

type StepStatus = "wait" | "process" | "finish" | "error";

interface StepItem {
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Overrides the status derived from this step's index vs `current`. */
  status?: StepStatus;
  icon?: React.ReactNode;
  /** antd keeps a disabled step unclickable even when `onChange` is set. */
  disabled?: boolean;
}

interface StepsProps
  extends Omit<React.HTMLAttributes<HTMLOListElement>, "onChange"> {
  current?: number;
  items?: StepItem[];
  /** antd applies this to the CURRENT step; the others follow `current`. */
  status?: StepStatus;
  /**
   * Present ⇒ the steps become clickable, as antd's `<Steps onChange>` does.
   * Omitted ⇒ they stay inert text, which is what the API-deployment wizard
   * wants.
   */
  onChange?: (current: number) => void;
  /** antd's token, not a DOM attribute — consumed rather than forwarded. */
  size?: SizeToken;
  /** The legacy `<Steps.Step>` children form. */
  children?: React.ReactNode;
}

interface PaginationProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  current?: number;
  pageSize?: number;
  total?: number;
  onChange?: (page: number, pageSize: number) => void;
  showSizeChanger?: boolean;
}

interface TreeNode {
  key: string;
  title?: React.ReactNode;
  icon?: React.ReactNode;
  /** A file rather than a directory: no switcher, never expandable. */
  isLeaf?: boolean;
  children?: TreeNode[];
}

interface TreeProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onSelect"> {
  treeData?: TreeNode[];
  onSelect?: (keys: string[], info: { node: TreeNode }) => void;
}

interface DirectoryTreeProps extends TreeProps {
  expandedKeys?: string[];
  selectedKeys?: string[];
  onExpand?: (keys: string[]) => void;
  /** Resolves once the node's children have been fetched into `treeData`. */
  loadData?: (node: TreeNode) => Promise<unknown> | void;
  switcherIcon?: React.ReactNode;
  /** `false` limits expanding to the switcher; antd's default is the row. */
  expandAction?: false | "click" | "doubleClick";
  showLine?: boolean;
  autoExpandParent?: boolean;
  rootClassName?: string;
}

interface DescriptionsProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title?: React.ReactNode;
  items?: Array<{
    key?: string;
    label?: React.ReactNode;
    children?: React.ReactNode;
  }>;
  column?: number;
  bordered?: boolean;
  /** antd appends a colon to the label of a NON-bordered Descriptions. */
  colon?: boolean;
  /*
   * Passed by two cloud plugins (`size="small"` / `"middle"`). Accepted
   * rather than forwarded — the DOM has no such attribute, and the density
   * comes from this shim's own classes.
   */
  size?: SizeToken;
}

interface StatisticProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title" | "prefix"> {
  title?: React.ReactNode;
  value?: React.ReactNode;
  /** Decimal places applied when `value` is numeric. */
  precision?: number;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  valueStyle?: React.CSSProperties;
}

interface FloatButtonProps
  extends Omit<React.HTMLAttributes<HTMLButtonElement>, "type"> {
  icon?: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  tooltip?: React.ReactNode;
  type?: "default" | "primary";
}

interface TransferItem {
  key: string;
  title?: React.ReactNode;
  disabled?: boolean;
}

interface TransferProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  dataSource?: TransferItem[];
  targetKeys?: string[];
  /** antd reports the new target keys, the direction, and what moved. */
  onChange?: (
    nextTargetKeys: string[],
    direction: "left" | "right",
    movedKeys: string[],
  ) => void;
  render?: (item: TransferItem) => React.ReactNode;
  titles?: [React.ReactNode, React.ReactNode];
  /** Adds a filter box to each panel. Both manual-review call-sites pass it. */
  showSearch?: boolean;
  locale?: { searchPlaceholder?: string; notFoundContent?: React.ReactNode };
  disabled?: boolean;
}

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  count?: number;
  /** Renders a dot instead of a number. */
  dot?: boolean;
  status?: "success" | "processing" | "default" | "error" | "warning";
  color?: string;
  /** Counts above this render as "N+". */
  overflowCount?: number;
  showZero?: boolean;
  offset?: [number, number];
}

const CardBase = React.forwardRef<HTMLDivElement, CardProps>(function Card(
  {
    title,
    extra,
    bordered = true,
    size,
    hoverable = false,
    className,
    styles,
    children,
    ...props
  },
  ref,
) {
  return (
    // The ant-* class names are emitted deliberately: this app has ~16 CSS
    // rules targeting `.ant-card-body` alone (heights, padding, overflow) and
    // more on head/extra. Without them those rules silently stop applying.
    <ShadcnCard
      ref={ref}
      className={cn(
        "ant-card",
        !bordered && "border-0 shadow-none",
        hoverable &&
          "cursor-pointer transition-shadow duration-200 hover:shadow-md",
        className,
      )}
      {...props}
    >
      {title || extra ? (
        <CardHeader
          className={cn(
            "ant-card-head flex-row items-center justify-between",
            size === "small" && "p-3",
          )}
        >
          {title ? (
            <CardTitle className="ant-card-head-title text-base">
              {title}
            </CardTitle>
          ) : (
            <span />
          )}
          {extra ? <div className="ant-card-extra">{extra}</div> : null}
        </CardHeader>
      ) : null}
      <CardContent
        className={cn("ant-card-body", size === "small" && "p-3 pt-0")}
      >
        {children}
      </CardContent>
    </ShadcnCard>
  );
});

/** antd `<Card.Meta avatar title description />`. */
function CardMeta({
  avatar,
  title,
  description,
  className,
}: {
  avatar?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("ant-card-meta flex items-start gap-3", className)}>
      {avatar}
      <div className="min-w-0">
        {title ? (
          <div className="ant-card-meta-title font-medium">{title}</div>
        ) : null}
        {description ? (
          <div className="ant-card-meta-description text-sm text-muted-foreground">
            {description}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * antd `<Tabs items activeKey onChange>`. Also supports the legacy
 * `<Tabs.TabPane>` children form.
 */
const TabsBase = React.forwardRef<HTMLDivElement, TabsProps>(function Tabs(
  {
    items,
    activeKey,
    defaultActiveKey,
    onChange,
    tabBarExtraContent,
    type,
    // Consumed, not forwarded: antd's token is not a DOM attribute.
    size: _size,
    className,
    children,
    "data-testid": testId,
    ...props
  },
  ref,
) {
  const panes =
    items ??
    React.Children.toArray(children)
      .filter(
        (
          c,
        ): c is React.ReactElement<{
          tabKey?: string;
          key?: string;
          tab?: React.ReactNode;
          icon?: React.ReactNode;
          children?: React.ReactNode;
          disabled?: boolean;
          "data-testid"?: string;
        }> => React.isValidElement(c),
      )
      .map((c) => ({
        /*
         * The ELEMENT's key, not `props.key` — React never puts `key` in
         * props, so reading it there yielded undefined for every pane and
         * nothing ever matched `activeKey`. CombinedOutput (the Output
         * Analyzer's profile tabs) uses `<Tabs.TabPane key=...>`, so its tabs
         * rendered permanently inactive with the panel `hidden`.
         *
         * `toArray` rewrites keys, and the prefix is NOT always ".$": children
         * arriving through a nested array — here a conditional pane followed by
         * a `.map()` — get ".N:$" instead. Strip either form, or the value
         * never matches antd's activeKey and the ".1:$…" string leaks out
         * through onChange as a profile id (that was the 500).
         */
        key: c.props.tabKey ?? String(c.key ?? "").replace(/^\.(\d+:)?\$/, ""),
        "data-testid": c.props["data-testid"],
        label: c.props.tab,
        // antd supports an icon on TabPane too, not just on `items`.
        icon: c.props.icon,
        children: c.props.children,
        disabled: c.props.disabled,
      }));

  const first = panes[0]?.key;

  return (
    <ShadcnTabs
      // Radix treats a present-but-undefined `value` as controlled, which
      // freezes the tabs. Pass EITHER value (antd's controlled activeKey) OR
      // defaultValue (uncontrolled), never both.
      {...(activeKey != null
        ? { value: String(activeKey) }
        : { defaultValue: String(defaultActiveKey ?? first ?? "") })}
      onValueChange={(v) => onChange?.(v)}
      className={cn("ant-tabs", className)}
      data-testid={testId}
      // Radix Root takes value/defaultValue/onValueChange/orientation only;
      // the remaining antd props are consumed above, not forwarded.
    >
      <div className="ant-tabs-nav flex items-center justify-between">
        {/*
         * antd's DEFAULT tab style is `line`: transparent strip, the active
         * label tinted and underlined. shadcn's primitive ships the `card`
         * look instead — a grey rounded pill with a raised active chip — which
         * is what Prompt Studio was rendering against the reference's
         * underline. `type="card"` opts back into the pill.
         *
         * Overridden here rather than in the primitive, so call-sites that
         * genuinely want shadcn's segmented tabs keep it.
         */}
        <TabsList
          className={cn(
            "ant-tabs-nav-list",
            type !== "card" &&
              "h-auto gap-4 rounded-none bg-transparent p-0 text-foreground",
          )}
        >
          {panes.map((p) => (
            <TabsTrigger
              key={String(p.key)}
              value={String(p.key)}
              data-testid={
                p["data-testid"] ??
                (testId && p.key != null ? `${testId}-tab-${p.key}` : undefined)
              }
              disabled={p.disabled}
              className={cn(
                type !== "card" &&
                  // Underline the active tab; keep the label tinted like antd.
                  "rounded-none border-b-2 border-transparent bg-transparent px-0 font-normal shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none",
                /*
                 * antd pads line-style tabs `12px 0`, giving a 46px nav. Two
                 * call-sites disagree about whether that is wanted:
                 *
                 *  - Standalone navs (Agentic Prompt Studio's project tabs,
                 *    Prompt Studio's left panel) want antd's height. Without
                 *    the padding they render 24px against the reference's 46px.
                 *  - The doc-manager toolbar centres its tabs against a file
                 *    name and buttons, and padding inflates the label's own box
                 *    so the TEXT rides above the row's centre line (`pb-2` gave
                 *    36px, `py-3` 48px, both ~5.6px off the file name).
                 *
                 * So pad by default and let that one toolbar opt out via CSS,
                 * rather than making every other nav wrong to suit it.
                 */
                type !== "card" && "py-3",
                // antd spaces the icon from its label; the base trigger has no
                // gap because it never expects two children.
                p.icon && "gap-2",
              )}
            >
              {/*
               * antd renders `items[].icon` before the label; the shim dropped
               * it, so the Dashboard's nested usage tabs (API Deployments, ETL
               * Pipelines, …) lost the icons the reference shows. `shrink-0`
               * keeps a lucide SVG from being squeezed by the label.
               */}
              {p.icon ? (
                <span className="flex shrink-0 items-center">{p.icon}</span>
              ) : null}
              {p.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabBarExtraContent}
      </div>
      {panes.map((p) => (
        <TabsContent
          key={String(p.key)}
          value={String(p.key)}
          className="ant-tabs-content ant-tabs-tabpane"
        >
          {p.children}
        </TabsContent>
      ))}
    </ShadcnTabs>
  );
});

function TabPane({
  children,
}: {
  tab?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return children ?? null;
}

// Written out so Tailwind sees the class names statically.
const LIST_GRID_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
  6: "grid-cols-6",
};

/**
 * antd `<List dataSource renderItem grid>`.
 *
 * `grid={{ column: n, gutter: g }}` switches antd from a stacked list to an
 * n-column grid. Ignoring it (and rendering a divided vertical list) makes
 * every adapter picker show one card per row in a tall scroller instead of a
 * 4-up grid — which is what happened on the Add LLM / Add Connector modals.
 */
const ListBase = React.forwardRef<HTMLDivElement, ListProps>(function List(
  {
    dataSource = [],
    renderItem,
    header,
    footer,
    grid,
    className,
    locale,
    ...props
  },
  ref,
) {
  const cols = grid?.column;
  const isGrid = cols != null;

  return (
    <div
      ref={ref}
      className={cn(
        // `divide-y` sets the border WIDTH but not its colour, and Tailwind's
        // default border colour is black. antd's list separator is a
        // near-invisible rgba(5,5,5,.06) hairline, so without `divide-border`
        // every row gained a solid black rule between it and the next.
        /*
         * `divide-separator` (#f0f0f0), not `divide-border` (#e5e5e5).
         * antd draws this separator as rgba(5,5,5,.06), which composites to
         * #f0f0f0 on white — a hairline. --border is four shades darker and
         * read as a hard rule between rows. Scoped here rather than by
         * retargeting --border, which also paints card edges and <Separator>
         * app-wide. The token is declared in index.css for light AND dark.
         */
        isGrid ? "grid" : "divide-y divide-separator",
        isGrid && LIST_GRID_COLS[cols as number],
        className,
      )}
      style={isGrid && grid?.gutter ? { gap: grid.gutter } : undefined}
      {...props}
    >
      {header ? <div className="py-2 font-medium">{header}</div> : null}
      {dataSource.length ? (
        dataSource.map((item, i) => (
          /*
           * NO vertical padding here.
           *
           * antd's `.ant-list-item` owns the 16px, and `renderItem` returns
           * that item — so padding the wrapper too stacks a second 16+16px on
           * top. An earlier pass set `py-4` here to match antd's 16px and
           * produced 114px rows against the reference's 82px: the item was
           * already correct at 82px and the wrapper added the surplus. `py-2`
           * before it was the same bug, just smaller (96px).
           *
           * Call-sites that need padding put it on their own row (ListView
           * uses `.cur-pointer { padding: 16px 0 }`), which is where antd
           * puts it too.
           */
          <div key={i}>{renderItem?.(item, i)}</div>
        ))
      ) : (
        <div className="ant-list-empty-text">
          {/* antd shows an <Empty> illustration here, not a bare string. */}
          {locale?.emptyText ? (
            locale.emptyText
          ) : (
            <Empty description="No data" />
          )}
        </div>
      )}
      {footer ? <div className="py-2">{footer}</div> : null}
    </div>
  );
});

/**
 * antd `<List.Item actions extra>`.
 *
 * BOTH trailing slots have to be honoured. antd's horizontal item renders
 * `children`, then `actions`, then `extra`; call-sites pick whichever reads
 * better and expect the same right-hand placement from either. Accepting only
 * `actions` let `extra` fall into `...props` and land on the <div> as an
 * unknown DOM attribute, so the node was dropped without an error — which is
 * how Share access lost the delete icon that revokes a user's or group's
 * access, leaving no way to un-share at all. Export Tool, Group members and
 * Co-owners lost their row controls the same way.
 */
function ListItem({
  actions,
  extra,
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  actions?: React.ReactNode[];
  extra?: React.ReactNode;
}) {
  return (
    <div
      className={cn("flex items-center justify-between gap-2", className)}
      {...props}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {actions?.length || extra ? (
        <div className="flex items-center gap-2">
          {actions}
          {extra}
        </div>
      ) : null}
    </div>
  );
}
function ListItemMeta({
  avatar,
  title,
  description,
}: {
  avatar?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      {avatar}
      <div className="min-w-0">
        {title ? <div className="font-medium">{title}</div> : null}
        {description ? (
          <div className="text-sm text-muted-foreground">{description}</div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * antd `<Layout>` and its slots.
 *
 * Three behaviours here are load-bearing, and all three caused real breakage
 * when they were missing:
 *
 * 1. `flex-auto` — antd's Layout is `flex: auto`, so a nested Layout grows to
 *    fill its parent. Without it the element computes `flex: 0 1 auto`, gets
 *    height 0, and every descendant using `flex: 1` collapses while still
 *    being present in the DOM.
 *
 * 2. `hasSider` — a Layout containing a Sider lays out as a ROW. antd detects
 *    this at RUNTIME via context, not by inspecting children, and that
 *    distinction matters: here the sider is rendered inside `<SideNavBar>`,
 *    so no amount of `React.Children` inspection can see it. A Sider therefore
 *    registers itself with the nearest Layout through context on mount.
 *
 * 3. `min-w-0` — the horizontal twin of the `min-h-0` beside it. A Layout is
 *    itself a flex item, and a flex item's automatic minimum size is its
 *    CONTENT's max-content width, so any page wide enough to overflow pushes
 *    the Layout past its track instead of scrolling inside it. That is not a
 *    few stray pixels: the agentic Prompt Studio nests percentage-width panes
 *    (`.pd-left-panel { width: 50% }`) around a table the DataTable gives
 *    `min-width: max-content` (antd `scroll={{ x: true }}`), and the two
 *    resolve against each other until the shell measures ~500,000px wide.
 *    Everything right of the viewport — the Export button, the PDF pane, five
 *    of the six status columns — was rendered, just off-screen.
 */
const SiderRegistryContext = React.createContext<(() => () => void) | null>(
  null,
);

const LayoutBase = React.forwardRef<HTMLDivElement, LayoutProps>(
  function Layout({ className, hasSider, children, ...props }, ref) {
    // A descendant Sider flips this on mount, however deeply it is nested.
    const [siderDetected, setSiderDetected] = React.useState(false);
    const register = React.useCallback(() => {
      setSiderDetected(true);
      return () => setSiderDetected(false);
    }, []);

    const isRow = hasSider ?? siderDetected;

    return (
      <SiderRegistryContext.Provider value={register}>
        <div
          ref={ref}
          className={cn(
            "flex min-h-0 min-w-0 flex-auto",
            isRow ? "flex-row" : "flex-col",
            className,
          )}
          {...props}
        >
          {children}
        </div>
      </SiderRegistryContext.Provider>
    );
  },
);

function Header({ className, ...p }: React.HTMLAttributes<HTMLElement>) {
  return <header className={cn("flex items-center", className)} {...p} />;
}
function Content({ className, ...p }: React.HTMLAttributes<HTMLElement>) {
  return <main className={cn("min-h-0 flex-auto", className)} {...p} />;
}
/**
 * antd `<Layout.Sider collapsible collapsed collapsedWidth width>`.
 *
 * The collapse props are behaviour, not decoration: when `collapsed` is set,
 * antd renders the sider at `collapsedWidth` instead of `width`. Dropping them
 * (as a plain `<aside {...props}>` does) leaves the rail at full width while
 * its call-site hides every label behind `!collapsed` — an icons-only sidebar
 * in a 240px gutter. They are also consumed here so `collapsible` /
 * `collapsedWidth` never reach the DOM as invalid attributes.
 */
interface SiderProps extends React.HTMLAttributes<HTMLElement> {
  width?: number | string;
  collapsed?: boolean;
  collapsedWidth?: number;
  collapsible?: boolean;
  /** `null` removes antd's built-in collapse handle. */
  trigger?: React.ReactNode;
  breakpoint?: "xs" | "sm" | "md" | "lg" | "xl" | "xxl";
  onCollapse?: (collapsed: boolean) => void;
}

function Sider({
  className,
  width = 200,
  collapsed,
  collapsedWidth = 80,
  collapsible,
  trigger,
  breakpoint,
  onCollapse,
  style,
  children,
  ...p
}: SiderProps) {
  // Tell the nearest ancestor Layout to lay out as a row (antd's hasSider).
  const register = React.useContext(SiderRegistryContext);
  React.useEffect(() => register?.(), [register]);

  return (
    <aside
      className={cn(
        "ant-layout-sider shrink-0 transition-[width] duration-200",
        collapsed && "ant-layout-sider-collapsed",
        className,
      )}
      style={{ width: collapsed ? collapsedWidth : width, ...style }}
      data-collapsed={collapsed ? "true" : undefined}
      // .ant-layout-sider-collapsed is styled by the app's CSS.
      data-sider=""
      {...p}
    >
      {/*
       * antd wraps a Sider's children in `.ant-layout-sider-children`, and
       * SideNavBar.css depends on it: that wrapper is the flex column which
       * clamps `.sidebar-content-wrapper` so its `overflow-y: auto` has
       * something to scroll against.
       *
       * Rendering children bare skipped the clamp, so the scroll wrapper grew
       * to its full content height (929px inside a 668px rail), `auto` never
       * engaged, and the bottom menu items were simply unreachable.
       */}
      <div className="ant-layout-sider-children">{children}</div>
    </aside>
  );
}
function Footer({ className, ...p }: React.HTMLAttributes<HTMLElement>) {
  return <footer className={className} {...p} />;
}

/**
 * antd's sentinel for "reject this file AND keep it out of the list", as
 * opposed to `false`, which only cancels the upload. Same literal antd uses,
 * so a call-site importing either one behaves identically.
 */
const LIST_IGNORE = "__LIST_IGNORE__";

/** Stable enough to key the rendered list and to match on removal. */
const fileUid = (file: File) =>
  `${file.name}-${file.size}-${file.lastModified}`;

/** antd `<Upload beforeUpload customRequest action>` over a hidden file input. */
const UploadBase = React.forwardRef<HTMLElement, UploadProps>(function Upload(
  {
    beforeUpload,
    customRequest,
    onChange,
    action,
    headers,
    name,
    accept,
    multiple,
    showUploadList,
    fileList,
    maxCount,
    onRemove,
    disabled,
    children,
    className,
    ...props
  },
  ref,
) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  const emit = (status: UploadFile["status"], file: File, response?: unknown) =>
    onChange?.({
      file: { name: file.name, status, response, originFileObj: file },
      fileList: fileList ?? [],
    });

  /**
   * antd hands the parsed body back as `info.file.response` on both the done
   * and error paths — Manage Documents reads `response.data[0]` for the new
   * document and `response.errors[0].detail` for the failure message, so a
   * non-JSON body has to degrade to text rather than throw.
   */
  const readBody = async (res: Response) => {
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  };

  /**
   * The `action` uploader. Without it the shim fell straight through to the
   * `!customRequest` branch below and reported `status: "done"` for a request
   * it had never sent: Manage Documents logged "File uploaded successfully"
   * and appended an empty row for every file, and nothing reached the server.
   */
  const uploadToAction = async (endpoint: string, file: File) => {
    emit("uploading", file);
    const body = new FormData();
    body.append(name ?? "file", file);
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: headers ?? {},
        body,
        credentials: "same-origin",
      });
      const payload = await readBody(res);
      emit(res.ok ? "done" : "error", file, payload);
    } catch (err) {
      emit("error", file, err);
    }
  };

  /**
   * antd's `maxCount`: a limit of 1 REPLACES the selection rather than
   * truncating it, which is what Verticals' request body relies on to let a
   * second pick swap the attached file.
   */
  const capped = (list: UploadFile[]) => {
    if (!maxCount) {
      return list;
    }
    return maxCount === 1 ? list.slice(-1) : list.slice(0, maxCount);
  };

  /**
   * Record a file the call-site will upload itself, and tell it so.
   *
   * antd's fileList is cumulative across selections, so a batch starts from
   * whatever the call-site is already holding rather than replacing it.
   */
  const stage = (staged: UploadFile[], file: File) => {
    const entry: UploadFile = {
      uid: fileUid(file),
      name: file.name,
      originFileObj: file,
    };
    const next = capped([...staged, entry]);
    onChange?.({ file: entry, fileList: next });
    return next;
  };

  const handleFiles = async (files: File[]) => {
    let staged: UploadFile[] = [...(fileList ?? [])];
    for (const file of files) {
      // antd aborts the upload when beforeUpload returns false, and equally
      // when the promise it returned rejects — Manage Documents rejects to
      // veto a duplicate file name, which used to surface as an unhandled
      // rejection that killed the rest of the loop.
      let proceed: boolean | unknown = true;
      if (beforeUpload) {
        try {
          proceed = await beforeUpload(file, files);
        } catch {
          continue;
        }
      }
      /*
       * antd has two distinct ways of saying no, and the shim honoured
       * neither correctly. `LIST_IGNORE` drops the file outright; anything
       * else that is not `false` means "go ahead and upload". Without the
       * constant, `Upload.LIST_IGNORE` was `undefined` at the call-site, so
       * Look-up Studio's oversize-file veto fell through to the success path
       * and reported a file it had just rejected as uploaded.
       */
      if (proceed === LIST_IGNORE) {
        continue;
      }
      if (proceed === false) {
        /*
         * `false` cancels only the UPLOAD — antd still adds the file to
         * fileList and still fires onChange. Import Project, Verticals'
         * request body and Simple Prompt Studio all veto the automatic
         * upload and submit the file themselves, so this onChange is the
         * ONLY way they ever learn a file was picked. Returning early here
         * left their fileList permanently empty: Import Project answered
         * "Please select a file to import" for the file the user had just
         * chosen, so the JSON could never be imported at all.
         */
        staged = stage(staged, file);
        continue;
      }
      if (customRequest) {
        customRequest({
          file,
          onSuccess: (body?: unknown) => emit("done", file, body),
          onError: (err?: unknown) => emit("error", file, err),
        });
      } else if (action) {
        await uploadToAction(action, file);
      } else {
        onChange?.({
          file: { name: file.name, status: "done", originFileObj: file },
          fileList: files,
        });
      }
    }
  };

  /** antd's remove button: `onRemove` may veto, otherwise the file drops out. */
  const removeFile = async (file: UploadFile) => {
    if (onRemove) {
      let keep: unknown;
      try {
        keep = await onRemove(file);
      } catch {
        return;
      }
      if (keep === false) {
        return;
      }
    }
    onChange?.({
      file: { ...file, status: "removed" },
      fileList: (fileList ?? []).filter((f) => f.uid !== file.uid),
    });
  };

  return (
    <span
      ref={ref}
      className={cn("inline-block", className)}
      {...props}
      // antd's Upload accepts dropped files, and Upload.Dragger's whole
      // purpose is to be a drop target — without this the dashed zone looked
      // droppable but silently ignored the file, and the browser navigated
      // away to render it instead.
      onDragOver={(e) => {
        e.preventDefault();
        props.onDragOver?.(e);
      }}
      onDrop={(e) => {
        e.preventDefault();
        if (!disabled) {
          handleFiles(Array.from(e.dataTransfer?.files ?? []));
        }
        props.onDrop?.(e);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          handleFiles(Array.from(e.target.files ?? []));
          // Clear the input so re-picking the same file fires change again;
          // otherwise retrying a failed upload silently does nothing.
          e.target.value = "";
        }}
      />
      <span
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={disabled ? -1 : 0}
        // A `role="button"` span gets no cursor from the browser at all, and
        // it is not a <button> so `buttonVariants` never reaches it.
        className={cn(disabled ? "cursor-not-allowed" : "cursor-pointer")}
      >
        {children ?? (
          <Button icon={<UploadIcon className="size-4" />}>Upload</Button>
        )}
      </span>
      {/*
       * antd's `.ant-upload-list`, on by default. It is the only feedback the
       * manual-submit call-sites give: with `beforeUpload` returning false
       * nothing else on screen changes when a file is picked, so Import
       * Project looked like it had ignored the JSON entirely.
       *
       * Rendered OUTSIDE the trigger span above — inside it, clicking the
       * remove button would also reopen the file picker.
       */}
      {showUploadList !== false && (fileList?.length ?? 0) > 0 && (
        <span className="ant-upload-list mt-2 block space-y-1 text-left">
          {fileList?.map((file) => (
            <span
              key={file.uid ?? file.name}
              className={cn(
                "flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/60",
                file.status === "error" && "text-destructive",
              )}
            >
              <Paperclip className="size-4 shrink-0 text-muted-foreground" />
              <span className="truncate">{file.name}</span>
              <button
                type="button"
                aria-label={`Remove ${file.name ?? "file"}`}
                className="ml-auto shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => removeFile(file)}
              >
                <X className="size-4" />
              </button>
            </span>
          ))}
        </span>
      )}
    </span>
  );
});

/**
 * antd `<Upload.Dragger>` — the large dashed drop zone.
 *
 * This was `Upload.Dragger = Upload`, which is not the same component: the
 * plain Upload renders an inline button-sized span, so the Import Project
 * modal showed its icon and help text floating with no drop target around
 * them, and dragging a file onto it did nothing because no drag handlers
 * existed at all.
 *
 * Reproduces antd's visuals (dashed border, tinted fill, hover/drag accent)
 * on Midnight Bloom tokens, and wires the drop events the name implies.
 */
const Dragger = React.forwardRef<HTMLElement, UploadProps>(function Dragger(
  { className, disabled, children, ...props },
  ref,
) {
  const [dragging, setDragging] = React.useState(false);

  return (
    <Upload
      ref={ref}
      disabled={disabled}
      className={cn("ant-upload-drag block w-full", className)}
      {...props}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) {
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={() => setDragging(false)}
    >
      <div
        className={cn(
          /*
           * antd's `.ant-upload-drag` is `padding: 16px 0` and takes its
           * height from the content. `py-10` (40px each side) made the
           * Manage Documents dropzone 114px tall for a single line of text,
           * dominating the modal.
           */
          "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-input bg-muted/40 px-4 py-4 text-center transition-colors",
          !disabled && "hover:border-primary",
          dragging && "border-primary bg-primary/5",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        {children}
      </div>
    </Upload>
  );
});

/** antd `<Result status title subTitle extra>`. */
const Result = React.forwardRef<HTMLDivElement, ResultProps>(function Result(
  {
    status = "info",
    title,
    subTitle,
    extra,
    icon,
    className,
    children,
    ...props
  },
  ref,
) {
  const Icon = status === "success" ? CircleCheck : CircleX;
  return (
    <div
      ref={ref}
      className={cn(
        "flex flex-col items-center gap-2 py-10 text-center",
        className,
      )}
      {...props}
    >
      {icon ?? (
        <Icon
          className={cn(
            "size-12",
            status === "success" ? "text-success" : "text-destructive",
          )}
        />
      )}
      {title ? (
        <div className="ant-result-title text-lg font-semibold">{title}</div>
      ) : null}
      {subTitle ? (
        <div className="ant-result-subtitle text-sm text-muted-foreground">
          {subTitle}
        </div>
      ) : null}
      {extra}
      {children}
    </div>
  );
});

/** antd `<Drawer open onClose placement>` → shadcn Sheet. */
const Drawer = React.forwardRef<HTMLDivElement, DrawerProps>(function Drawer(
  {
    open,
    onClose,
    title,
    placement = "right",
    width,
    closable = true,
    styles,
    // Consumed, not forwarded — see DrawerProps.
    destroyOnClose: _destroyOnClose,
    className,
    children,
    ...props
  },
  ref,
) {
  /*
   * antd's `width` is the panel's actual width; mapping it to `max-width` left
   * the Sheet on its `w-3/4` default, so `width="85%"` silently rendered 75%.
   * `max-width: 100%` goes with it to beat the variant's `sm:max-w-sm` (384px),
   * which would otherwise clamp any width past that. antd applies `width` to
   * side drawers only — top/bottom ones are sized by `height`, which no
   * call-site passes.
   */
  const isSideDrawer = placement === "left" || placement === "right";
  const sizing =
    width !== undefined && isSideDrawer
      ? { width, maxWidth: "100%" as const }
      : undefined;

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose?.()}>
      <SheetContent
        ref={ref}
        side={placement}
        showClose={closable}
        style={sizing}
        /*
         * `p-0` + a padded body, rather than padding on the panel itself.
         * antd pads the BODY, so a call-site clearing it (`styles.body`) gets a
         * full-bleed panel; with the padding on the panel, a drawer whose
         * header carries its own background floated inset with a 24px frame of
         * page around it. `flex-col` + `flex-1` reproduces antd's scrolling
         * body under a fixed header.
         */
        className={cn("flex flex-col gap-0 p-0", className)}
        {...props}
      >
        {title ? (
          <SheetHeader className="shrink-0 border-b px-6 py-4">
            <SheetTitle>{title}</SheetTitle>
          </SheetHeader>
        ) : null}
        <div className="min-h-0 flex-1 overflow-auto p-6" style={styles?.body}>
          {children}
        </div>
      </SheetContent>
    </Sheet>
  );
});

/** antd `<Segmented options value onChange>`. */
const Segmented = React.forwardRef<HTMLDivElement, SegmentedProps>(
  function Segmented(
    {
      options = [],
      value,
      onChange,
      className,
      "data-testid": testId,
      ...props
    },
    ref,
  ) {
    return (
      <div
        ref={ref}
        className={cn("inline-flex gap-1 rounded-md bg-muted p-1", className)}
        data-segmented=""
        data-testid={testId}
        {...props}
      >
        {options.map((o) => {
          const val = typeof o === "object" ? o.value : o;
          const label = typeof o === "object" ? o.label : o;
          return (
            /*
             * Segments are repeated controls built from `options`, so they
             * cannot be labelled from the call-site. The ids derive from the
             * parent's, as Tabs and Dropdown do, so a call-site opts in once.
             *
             * NOTE: this makes each segment selectable, not the ACTIVE one
             * assertable — which segment is selected is still expressed only
             * by the Tailwind classes below. Exposing that state would mean
             * adding an attribute rather than a test id, which is out of scope
             * for this pass.
             */
            <button
              key={String(val)}
              type="button"
              data-testid={testId ? `${testId}-option-${val}` : undefined}
              onClick={() => onChange?.(val)}
              className={cn(
                // `whitespace-nowrap`: antd segments never wrap. Without it a
                // two-word label breaks mid-control the moment the segmented
                // sits in a tight row — the agentic Prompt Studio's document
                // pane rendered "Raw Text" as "Raw" over "Text", stacking the
                // whole toolbar to two lines.
                "ant-segmented-item cursor-pointer whitespace-nowrap rounded px-3 py-1 text-sm disabled:cursor-not-allowed",
                String(value) === String(val)
                  ? "bg-background shadow-sm"
                  : "text-muted-foreground",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>
    );
  },
);

/** antd `<Menu items onClick>` — a simple vertical list. */
const MenuBase = React.forwardRef<HTMLDivElement, MenuProps>(function Menu(
  {
    items = [],
    selectedKeys = [],
    onClick,
    onSelect,
    mode,
    className,
    ...props
  },
  ref,
) {
  return (
    <nav ref={ref} className={cn("flex flex-col gap-1", className)} {...props}>
      {items.filter(Boolean).map((item) => (
        <button
          key={String(item.key)}
          type="button"
          disabled={item.disabled}
          onClick={() => {
            const key = String(item.key);
            onClick?.({ key });
            // Single-select, as antd's Menu is by default: the new selection
            // is just this key.
            onSelect?.({ key, keyPath: [key], selectedKeys: [key] });
          }}
          className={cn(
            "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent disabled:cursor-not-allowed",
            /*
             * antd marks the selected item with a PRIMARY tint and primary
             * text (colorPrimaryBg + colorPrimary), not a grey. `bg-accent`
             * resolved to the same #f5f5f5 as the hover state, so the active
             * settings page was indistinguishable from an idle one.
             */
            selectedKeys.includes(String(item.key)) &&
              "bg-[var(--violet-50)] font-medium text-primary hover:bg-[var(--violet-50)]",
          )}
        >
          {/*
           * The icon needs its own shrink-0 box. Dropped straight into the
           * flex row, a long label squeezes the SVG to width 0 while leaving
           * its height at 24 — "SummarizedExtraction" in the Prompt Studio
           * settings menu rendered as a blank gap where every shorter
           * sibling showed its icon. antd wraps the icon for the same reason.
           */}
          {item.icon ? (
            <span className="flex shrink-0 items-center">{item.icon}</span>
          ) : null}
          <span className="truncate">{item.label}</span>
        </button>
      ))}
    </nav>
  );
});
function MenuItem({ children }: { children?: React.ReactNode }) {
  return children ?? null;
}

/**
 * antd `<Menu.ItemGroup title>` — a labelled group of items.
 *
 * Rendered by the verticals Playground plugin. Missing it is the same latent
 * React #130 that `Skeleton.Button` caused on the Agentic Prompt Studio route:
 * an undefined element type takes down the whole page, not just the menu.
 */
function MenuItemGroup({
  title,
  children,
}: {
  title?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="ant-menu-item-group">
      {title ? (
        <div className="ant-menu-item-group-title px-3 py-1.5 text-xs text-muted-foreground">
          {title}
        </div>
      ) : null}
      <div className="ant-menu-item-group-list">{children}</div>
    </div>
  );
}

/**
 * antd's `<Skeleton.Button>` / `<Skeleton.Input>` — single-element placeholders
 * sized like the control they stand in for, rather than the paragraph block
 * `<Skeleton>` renders.
 *
 * Their absence took down the whole Agentic Prompt Studio project route:
 * rendering an undefined component is React error #130, which the error
 * boundary reports as "Couldn't load this page" with no clue which component
 * was missing.
 */
const SKELETON_BLOCK_SIZES = {
  small: "h-6",
  default: "h-8",
  large: "h-10",
} as const;

interface SkeletonBlockProps extends React.HTMLAttributes<HTMLDivElement> {
  /** antd sizes these by control height, not by content. */
  size?: keyof typeof SKELETON_BLOCK_SIZES;
  /** antd's shimmer toggle; the shadcn primitive always animates. */
  active?: boolean;
  block?: boolean;
  shape?: "circle" | "round" | "square" | "default";
}

function SkeletonButton({
  size = "default",
  active: _active,
  block,
  shape,
  className,
  ...props
}: SkeletonBlockProps) {
  return (
    <ShadcnSkeleton
      className={cn(
        SKELETON_BLOCK_SIZES[size] ?? SKELETON_BLOCK_SIZES.default,
        block ? "w-full" : "w-16",
        shape === "circle" ? "rounded-full" : "rounded-md",
        className,
      )}
      {...props}
    />
  );
}

function SkeletonInput({
  size = "default",
  active: _active,
  block,
  className,
  ...props
}: SkeletonBlockProps) {
  return (
    <ShadcnSkeleton
      className={cn(
        SKELETON_BLOCK_SIZES[size] ?? SKELETON_BLOCK_SIZES.default,
        // antd's Input skeleton spans its container unless told otherwise;
        // the call-sites rely on that to fill a panel row.
        block === false ? "w-40" : "w-full",
        "rounded-md",
        className,
      )}
      {...props}
    />
  );
}

/** antd `<Skeleton active paragraph />`. */
const SkeletonBase = React.forwardRef<HTMLDivElement, SkeletonProps>(
  function Skeleton(
    { active, paragraph, title = true, className, ...props },
    ref,
  ) {
    const rows = typeof paragraph === "object" ? (paragraph.rows ?? 3) : 3;
    return (
      <div ref={ref} className={cn("space-y-2", className)} {...props}>
        {title ? <ShadcnSkeleton className="h-5 w-1/3" /> : null}
        {Array.from({ length: rows }).map((_, i) => (
          <ShadcnSkeleton key={i} className="h-4 w-full" />
        ))}
      </div>
    );
  },
);

/*
 * Object.assign so the statics stay part of the inferred type — same reason as
 * Card.Meta and Collapse.Panel. `<Skeleton.Button>` must type-check AND remain
 * resolvable by value, because the shim-completeness guard reads it that way.
 */
const Skeleton = Object.assign(SkeletonBase, {
  Button: SkeletonButton,
  Input: SkeletonInput,
});

/** One `<Steps.Step>`; the parent reads its props, so it renders nothing. */
function Step(_props: StepItem) {
  return null;
}

/** Written out so Tailwind sees the class names statically. */
const STEP_MARKER: Record<StepStatus, string> = {
  wait: "bg-muted text-muted-foreground",
  process: "bg-primary text-primary-foreground",
  finish: "bg-primary/15 text-primary",
  error: "bg-destructive text-white",
};

/**
 * antd derives a step's status from its index against `current`, unless the
 * item carries its own — which the cloud onboarding stepper does for all five.
 * The top-level `status` prop applies to the current step only.
 */
function resolveStepStatus(
  item: StepItem,
  index: number,
  current: number,
  overall: StepStatus | undefined,
): StepStatus {
  if (item.status) {
    return item.status;
  }
  if (index === current) {
    return overall ?? "process";
  }
  return index < current ? "finish" : "wait";
}

/**
 * antd `<Steps current items>`. Also supports the legacy `<Steps.Step>`
 * children form, which CreateApiDeploymentFromPromptStudio uses.
 */
const StepsBase = React.forwardRef<HTMLOListElement, StepsProps>(function Steps(
  {
    current = 0,
    items,
    status,
    onChange,
    // Consumed, not forwarded: antd's token is not a DOM attribute.
    size: _size,
    className,
    children,
    ...props
  },
  ref,
) {
  const entries: StepItem[] =
    items ??
    React.Children.toArray(children)
      .filter((c): c is React.ReactElement<StepItem> => React.isValidElement(c))
      .map((c) => ({
        title: c.props.title,
        description: c.props.description,
        status: c.props.status,
        icon: c.props.icon,
        disabled: c.props.disabled,
      }));

  return (
    <ol
      ref={ref}
      className={cn("flex items-center gap-4", className)}
      {...props}
    >
      {entries.map((item, i) => {
        const stepStatus = resolveStepStatus(item, i, current, status);
        const body = (
          <>
            <span
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full text-xs",
                STEP_MARKER[stepStatus],
              )}
            >
              {item.icon ??
                (stepStatus === "finish" ? (
                  <Check className="size-3.5" />
                ) : stepStatus === "error" ? (
                  <X className="size-3.5" />
                ) : (
                  i + 1
                ))}
            </span>
            <span className="flex flex-col items-start text-left">
              <span
                className={cn(
                  "text-sm",
                  stepStatus === "process" && "font-medium",
                  stepStatus === "error" && "text-destructive",
                )}
              >
                {item.title}
              </span>
              {item.description ? (
                <span className="text-xs text-muted-foreground">
                  {item.description}
                </span>
              ) : null}
            </span>
          </>
        );

        return (
          // Index key: steps are a fixed ordered list, and titles repeat.
          <li key={i}>
            {onChange && !item.disabled ? (
              <button
                type="button"
                className="flex cursor-pointer items-center gap-2 rounded"
                aria-current={stepStatus === "process" ? "step" : undefined}
                onClick={() => onChange(i)}
              >
                {body}
              </button>
            ) : (
              <span
                className="flex items-center gap-2"
                aria-current={stepStatus === "process" ? "step" : undefined}
              >
                {body}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
});

/** antd `<Pagination current pageSize total onChange>`. */
const Pagination = React.forwardRef<HTMLDivElement, PaginationProps>(
  function Pagination(
    {
      current = 1,
      pageSize = 10,
      total = 0,
      onChange,
      showSizeChanger,
      className,
      ...props
    },
    ref,
  ) {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    return (
      <div
        ref={ref}
        className={cn("flex items-center justify-end gap-2 text-sm", className)}
        {...props}
      >
        <Button
          size="small"
          disabled={current <= 1}
          onClick={() => onChange?.(current - 1, pageSize)}
        >
          Previous
        </Button>
        <span className="text-muted-foreground">
          Page {current} of {pages}
        </span>
        <Button
          size="small"
          disabled={current >= pages}
          onClick={() => onChange?.(current + 1, pageSize)}
        >
          Next
        </Button>
      </div>
    );
  },
);

/** antd `<Tree treeData>` — a shallow nested list; no call-site drags nodes. */
const TreeBase = React.forwardRef<HTMLDivElement, TreeProps>(function Tree(
  { treeData = [], onSelect, className, ...props },
  ref,
) {
  const renderNodes = (nodes: TreeNode[], depth = 0): React.ReactNode =>
    nodes.map((n: TreeNode) => (
      <div key={String(n.key)} style={{ paddingLeft: depth * 12 }}>
        <button
          type="button"
          className="cursor-pointer rounded px-1 py-0.5 text-left text-sm hover:bg-accent"
          onClick={() => onSelect?.([n.key], { node: n })}
        >
          {n.title}
        </button>
        {n.children ? renderNodes(n.children, depth + 1) : null}
      </div>
    ));

  return (
    <div ref={ref} className={className} {...props}>
      {renderNodes(treeData)}
    </div>
  );
});

/**
 * antd `<Tree.DirectoryTree>` — the file browser in the Configure Connector
 * modal, which is the only call-site.
 *
 * It cannot share TreeBase: that one renders every node expanded and has no
 * notion of `loadData`, but the connector browser lists one directory at a
 * time and fetches a folder's children the first time it is opened. The
 * folders come back childless, so without `loadData` the tree is a flat list
 * of unopenable directories.
 *
 * `expandedKeys`/`selectedKeys` fall back to internal state when the
 * call-site omits them, because antd supports both forms and FileExplorer
 * only happens to drive the controlled one.
 */
const DirectoryTree = React.forwardRef<HTMLDivElement, DirectoryTreeProps>(
  function DirectoryTree(
    {
      treeData = [],
      expandedKeys,
      selectedKeys,
      onExpand,
      onSelect,
      loadData,
      switcherIcon,
      /*
       * antd's DirectoryTree expands a directory when its ROW is clicked;
       * `expandAction={false}` restricts that to the switcher. FileExplorer
       * passes false so that picking a destination folder does not also
       * expand it.
       */
      expandAction = "click",
      // Consumed, not forwarded: antd chrome flags, not DOM attributes.
      showLine: _showLine,
      autoExpandParent: _autoExpandParent,
      rootClassName,
      className,
      ...props
    },
    ref,
  ) {
    const [ownExpandedKeys, setOwnExpandedKeys] = React.useState<string[]>([]);
    const [ownSelectedKeys, setOwnSelectedKeys] = React.useState<string[]>([]);
    const [loadingKeys, setLoadingKeys] = React.useState<string[]>([]);

    const expanded = expandedKeys ?? ownExpandedKeys;
    const selected = selectedKeys ?? ownSelectedKeys;

    const toggle = (node: TreeNode) => {
      const isOpen = expanded.includes(node.key);
      const next = isOpen
        ? expanded.filter((k) => k !== node.key)
        : [...expanded, node.key];
      setOwnExpandedKeys(next);
      onExpand?.(next);

      // antd fetches a node's children on first expand only — `children`
      // being set is what marks it already loaded.
      if (isOpen || node.children || !loadData) {
        return;
      }
      setLoadingKeys((keys) => [...keys, node.key]);
      Promise.resolve(loadData(node))
        .catch(() => {
          // The call-site surfaces its own load error; this only clears the
          // spinner so the switcher does not stay stuck.
        })
        .finally(() => {
          setLoadingKeys((keys) => keys.filter((k) => k !== node.key));
        });
    };

    const select = (node: TreeNode) => {
      const next = [node.key];
      setOwnSelectedKeys(next);
      onSelect?.(next, { node });
    };

    const renderNodes = (nodes: TreeNode[], depth = 0): React.ReactNode =>
      nodes.map((node) => {
        const isOpen = expanded.includes(node.key);
        const isSelected = selected.includes(node.key);
        return (
          <div key={String(node.key)}>
            <div
              role="treeitem"
              tabIndex={0}
              aria-selected={isSelected}
              aria-expanded={node.isLeaf ? undefined : isOpen}
              className={cn(
                "flex cursor-pointer items-center gap-1 rounded py-0.5 pe-1 text-sm hover:bg-accent",
                isSelected && "bg-accent text-accent-foreground",
              )}
              style={{ paddingInlineStart: depth * 12 + 4 }}
              onClick={() => {
                select(node);
                if (expandAction === "click" && !node.isLeaf) {
                  toggle(node);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  select(node);
                }
              }}
            >
              {node.isLeaf ? (
                <span className="size-[18px] shrink-0" />
              ) : (
                <button
                  type="button"
                  aria-label={isOpen ? "Collapse" : "Expand"}
                  className={cn(
                    "flex size-[18px] shrink-0 items-center justify-center transition-transform",
                    !isOpen && "-rotate-90",
                  )}
                  onClick={(e) => {
                    // Without this the row handler also fires and, when
                    // `expandAction` is "click", immediately toggles back.
                    e.stopPropagation();
                    toggle(node);
                  }}
                >
                  {loadingKeys.includes(node.key) ? (
                    <LoaderCircle className="size-3 animate-spin" />
                  ) : (
                    (switcherIcon ?? <ChevronDown className="size-3" />)
                  )}
                </button>
              )}
              {node.icon ? (
                <span className="flex size-4 shrink-0 items-center justify-center">
                  {node.icon}
                </span>
              ) : null}
              {/* min-w-0 so the name column's `ellipsis` has something to
                  shrink against instead of overflowing the panel. */}
              <span className="min-w-0 flex-1">{node.title}</span>
            </div>
            {/* role="group" so children report their real depth; without it
                every row is announced as level 1 regardless of nesting. */}
            {isOpen && node.children ? (
              <div role="group">{renderNodes(node.children, depth + 1)}</div>
            ) : null}
          </div>
        );
      });

    return (
      <div
        ref={ref}
        role="tree"
        className={cn(rootClassName, className)}
        {...props}
      >
        {renderNodes(treeData)}
      </div>
    );
  },
);

/** One `<Descriptions.Item>`, however the call-site supplied it. */
type DescriptionEntry = NonNullable<DescriptionsProps["items"]>[number];

/**
 * antd's cell padding is `padding paddingLG`, stepped down a token per size:
 * 16/24 by default, 12/24 for "middle", 8/16 for "small".
 */
function cellPadding(size: SizeToken | undefined) {
  if (size === "small") {
    return "px-4 py-2";
  }
  return size === "middle" ? "px-6 py-3" : "px-6 py-4";
}

/** antd's `itemPaddingBottom`, which spaces the rows of a plain Descriptions. */
function itemPaddingBottom(size: SizeToken | undefined) {
  if (size === "small") {
    return "pb-2";
  }
  return size === "middle" ? "pb-3" : "pb-4";
}

/** `items` and `<Descriptions.Item>` children are two spellings of one list. */
function toEntries(
  items: DescriptionsProps["items"],
  children: React.ReactNode,
): DescriptionEntry[] {
  if (items) {
    return items;
  }
  return React.Children.toArray(children)
    .filter((c): c is React.ReactElement<DescriptionEntry> =>
      React.isValidElement(c),
    )
    .map((c, i) => ({
      key: String(c.key ?? i),
      label: c.props.label,
      children: c.props.children,
    }));
}

/**
 * antd `<Descriptions>` — a label/value grid. Only cloud plugins use it, but it
 * lives here per D9 so both repos share one implementation.
 *
 * antd renders it as a real <table>: a row per `column` items, with the label
 * BESIDE its value — a `<th>` when `bordered`, an inline `<span>` and a colon
 * when not. The first pass emitted a <dl> of stacked label-above-value pairs
 * instead, which cost LLMWhisperer's billing page its pricing table: each plan
 * card listed the four processing modes and their prices as loose text, and the
 * two plugin CSS rules that hook antd's own DOM matched nothing — `.pricing-table
 * th` (label cell transparent, not grey) and the free card's
 * `.ant-descriptions-item-content { display: none }`, which is what leaves that
 * card showing mode names without prices.
 */
const DescriptionsBase = React.forwardRef<HTMLDivElement, DescriptionsProps>(
  function Descriptions(
    {
      title,
      items,
      column = 3,
      bordered,
      size,
      colon = true,
      className,
      children,
      ...props
    },
    ref,
  ) {
    const entries = toEntries(items, children);
    const rows: DescriptionEntry[][] = [];
    for (let i = 0; i < entries.length; i += column) {
      rows.push(entries.slice(i, i + column));
    }

    const padding = bordered ? cellPadding(size) : itemPaddingBottom(size);

    return (
      <div
        ref={ref}
        className={cn(
          "ant-descriptions w-full",
          bordered && "ant-descriptions-bordered",
          className,
        )}
        {...props}
      >
        {title ? (
          <div className="ant-descriptions-header mb-2 font-medium">
            {title}
          </div>
        ) : null}
        <div
          className={cn(
            "ant-descriptions-view",
            /*
             * The rounding has to clip the corner cells, and the outer border
             * belongs to this wrapper so the cells only draw the dividers
             * BETWEEN themselves — otherwise every edge doubles up.
             */
            bordered && "overflow-hidden rounded-lg border border-separator",
          )}
        >
          {/*
           * Deliberately NOT `table-fixed`: antd sizes these columns to their
           * content, which is what lets a long label like "High Quality with
           * Form Elements / Table" take the width it needs.
           */}
          <table className="w-full border-collapse">
            <tbody>
              {rows.map((row, r) => (
                <tr
                  key={row.map((item) => String(item.key ?? item.label)).join()}
                  className="ant-descriptions-row"
                >
                  {row.map((item, c) =>
                    bordered ? (
                      <React.Fragment key={String(item.key ?? item.label)}>
                        <th
                          className={cn(
                            "ant-descriptions-item-label text-start align-top text-sm font-normal text-muted-foreground",
                            // antd's `labelBg` — a wash, not an opaque grey, so
                            // it tints whatever the surface underneath is.
                            "bg-black/[0.02]",
                            padding,
                            r < rows.length - 1 && "border-b border-separator",
                            "border-r border-separator",
                          )}
                        >
                          {item.label}
                        </th>
                        <td
                          className={cn(
                            "ant-descriptions-item-content align-top text-sm",
                            padding,
                            r < rows.length - 1 && "border-b border-separator",
                            c < row.length - 1 && "border-r border-separator",
                          )}
                        >
                          {item.children}
                        </td>
                      </React.Fragment>
                    ) : (
                      <td
                        key={String(item.key ?? item.label)}
                        className={cn(
                          "ant-descriptions-item align-top",
                          r < rows.length - 1 && padding,
                        )}
                      >
                        <div className="ant-descriptions-item-container flex text-sm">
                          <span
                            className={cn(
                              "ant-descriptions-item-label me-2 shrink-0 text-muted-foreground",
                              /*
                               * antd hangs the colon off ::after, so the label's
                               * own text stays exactly what the call-site wrote
                               * — a `getByText("Owner")` still matches.
                               */
                              colon && "after:ms-px after:content-[':']",
                            )}
                          >
                            {item.label}
                          </span>
                          <span className="ant-descriptions-item-content min-w-0">
                            {item.children}
                          </span>
                        </div>
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  },
);

/**
 * A marker only: `<Descriptions>` reads `label`/`children` off these elements
 * and lays the cells out itself, exactly as antd does. Rendering it standalone
 * would emit a row with no table around it, so it renders nothing.
 */
function DescriptionsItem(_props: {
  label?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return null;
}

/** antd `<Statistic title value prefix suffix precision />`. */
const Statistic = React.forwardRef<HTMLDivElement, StatisticProps>(
  function Statistic(
    {
      title,
      value,
      precision,
      prefix,
      suffix,
      valueStyle,
      className,
      ...props
    },
    ref,
  ) {
    const shown =
      typeof value === "number" && precision != null
        ? value.toFixed(precision)
        : value;
    return (
      <div ref={ref} className={cn("space-y-1", className)} {...props}>
        {title ? (
          <div className="text-sm text-muted-foreground">{title}</div>
        ) : null}
        <div
          className="flex items-baseline gap-1 text-2xl font-semibold"
          style={valueStyle}
        >
          {prefix}
          <span>{shown}</span>
          {suffix ? <span className="text-base">{suffix}</span> : null}
        </div>
      </div>
    );
  },
);

/** antd `<FloatButton icon onClick tooltip />`. */
const FloatButtonBase = React.forwardRef<HTMLButtonElement, FloatButtonProps>(
  function FloatButton(
    { icon, onClick, tooltip, type, className, children, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type="button"
        title={typeof tooltip === "string" ? tooltip : undefined}
        onClick={onClick}
        className={cn(
          "fixed bottom-6 right-6 z-50 flex size-11 cursor-pointer items-center justify-center rounded-full shadow-lg",
          type === "primary"
            ? "bg-primary text-primary-foreground"
            : "border bg-background text-foreground",
          className,
        )}
        {...props}
      >
        {icon ?? children}
      </button>
    );
  },
);
function FloatButtonGroup({ children }: { children?: React.ReactNode }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {children}
    </div>
  );
}

/**
 * antd `<Transfer>` — dual list with move-between controls.
 *
 * antd's Transfer is a CHECKBOX-selection widget: you tick rows in one panel,
 * then press the arrow between the panels to move the checked set. The earlier
 * stub moved a row on click and rendered neither checkboxes, item counts,
 * search, nor the arrows — so against the reference it read as a plain list
 * and `showSearch` (which the manual-review call-sites pass) did nothing.
 */
const Transfer = React.forwardRef<HTMLDivElement, TransferProps>(
  function Transfer(
    {
      dataSource = [],
      targetKeys = [],
      onChange,
      render,
      titles = ["Source", "Target"],
      showSearch,
      locale,
      disabled,
      className,
      ...props
    },
    ref,
  ) {
    const inTarget = React.useMemo(() => new Set(targetKeys), [targetKeys]);
    // Checked rows, tracked per side so the arrows know what to move.
    const [checked, setChecked] = React.useState<Set<string>>(new Set());
    const [search, setSearch] = React.useState({ left: "", right: "" });

    const source = dataSource.filter((d) => !inTarget.has(d.key));
    const target = dataSource.filter((d) => inTarget.has(d.key));

    const label = (item: TransferItem) =>
      render ? render(item) : (item.title ?? item.key);

    const matches = (item: TransferItem, term: string) => {
      if (!term) {
        return true;
      }
      const text =
        typeof item.title === "string" ? item.title : String(item.key);
      return text.toLowerCase().includes(term.toLowerCase());
    };

    const visible = (entries: TransferItem[], side: "left" | "right") =>
      entries.filter((e) => matches(e, search[side]));

    const toggle = (key: string) => {
      setChecked((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
        }
        return next;
      });
    };

    const move = (toTarget: boolean) => {
      const from = toTarget ? source : target;
      const moving = from.filter((d) => checked.has(d.key)).map((d) => d.key);
      if (!moving.length) {
        return;
      }
      const next = toTarget
        ? [...targetKeys, ...moving]
        : targetKeys.filter((k) => !moving.includes(k));
      onChange?.(next, toTarget ? "right" : "left", moving);
      // antd clears the selection of whichever side just moved.
      setChecked((prev) => {
        const rest = new Set(prev);
        for (const k of moving) {
          rest.delete(k);
        }
        return rest;
      });
    };

    const column = (
      title: React.ReactNode,
      entries: TransferItem[],
      side: "left" | "right",
    ) => {
      const rows = visible(entries, side);
      const selectable = entries.filter((e) => !e.disabled);
      const allChecked =
        selectable.length > 0 && selectable.every((e) => checked.has(e.key));
      const someChecked = selectable.some((e) => checked.has(e.key));

      const toggleAll = () => {
        setChecked((prev) => {
          const next = new Set(prev);
          for (const e of selectable) {
            if (allChecked) {
              next.delete(e.key);
            } else {
              next.add(e.key);
            }
          }
          return next;
        });
      };

      return (
        <div className="ant-transfer-list flex min-w-0 flex-1 flex-col rounded-md border">
          {/* antd's header: select-all on the left, count, then the title. */}
          <div className="ant-transfer-list-header flex items-center gap-2 border-b px-3 py-2 text-sm">
            <Checkbox
              checked={
                allChecked ? true : someChecked ? "indeterminate" : false
              }
              onCheckedChange={toggleAll}
              disabled={disabled || !selectable.length}
              aria-label={`Select all in ${
                typeof title === "string" ? title : side
              }`}
            />
            <span className="text-muted-foreground">
              {someChecked
                ? `${selectable.filter((e) => checked.has(e.key)).length}/${entries.length} items`
                : `${entries.length} items`}
            </span>
            <span className="ml-auto truncate font-medium">{title}</span>
          </div>

          {showSearch ? (
            <div className="border-b p-2">
              <Input
                value={search[side]}
                placeholder={locale?.searchPlaceholder ?? "Search here"}
                disabled={disabled}
                onChange={(e) =>
                  setSearch((prev) => ({ ...prev, [side]: e.target.value }))
                }
                className="h-8 text-sm"
              />
            </div>
          ) : null}

          <div className="ant-transfer-list-body max-h-64 overflow-auto">
            {rows.length ? (
              rows.map((item) => (
                <label
                  key={String(item.key)}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent",
                    (item.disabled || disabled) &&
                      "cursor-not-allowed opacity-50",
                  )}
                >
                  <Checkbox
                    checked={checked.has(item.key)}
                    disabled={item.disabled || disabled}
                    onCheckedChange={() => toggle(item.key)}
                  />
                  <span className="min-w-0 truncate">{label(item)}</span>
                </label>
              ))
            ) : (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                {locale?.notFoundContent ?? "No data"}
              </div>
            )}
          </div>
        </div>
      );
    };

    const canMoveRight = source.some((d) => checked.has(d.key));
    const canMoveLeft = target.some((d) => checked.has(d.key));

    return (
      <div
        ref={ref}
        className={cn("ant-transfer flex items-center gap-2", className)}
        {...props}
      >
        {column(titles[0], source, "left")}
        {/* The arrows sit BETWEEN the panels, as in antd — moving the checked
            set rather than the row that happened to be clicked. */}
        <div className="flex shrink-0 flex-col gap-1">
          <button
            type="button"
            aria-label="Move selected to the right"
            disabled={disabled || !canMoveRight}
            onClick={() => move(true)}
            className="inline-flex size-6 items-center justify-center rounded border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronRight className="size-3" />
          </button>
          <button
            type="button"
            aria-label="Move selected to the left"
            disabled={disabled || !canMoveLeft}
            onClick={() => move(false)}
            className="inline-flex size-6 items-center justify-center rounded border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronLeft className="size-3" />
          </button>
        </div>
        {column(titles[1], target, "right")}
      </div>
    );
  },
);

/**
 * antd `<Badge count dot status>` — a small counter/dot overlaid on its child.
 * Distinct from shadcn's `Badge` (a pill label), which is what antd calls Tag.
 *
 * `style` targets the COUNT, not the wrapper. antd documents it that way, and
 * call-sites rely on it: PromptChangeIndicator passes
 * `style={{ backgroundColor: color }}` to tint its counter. Letting `style`
 * fall through `{...props}` onto the wrapper span painted a solid grey block
 * behind the icon button on every prompt card in Prompt Studio.
 */
const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  {
    count,
    dot,
    status,
    color,
    overflowCount = 99,
    showZero,
    offset,
    className,
    style,
    children,
    ...props
  },
  ref,
) {
  const shown =
    typeof count === "number" && count > overflowCount
      ? `${overflowCount}+`
      : count;
  const visible = dot || (count != null && (count !== 0 || showZero));

  if (!children) {
    return visible ? (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-full bg-destructive px-1.5 text-xs text-destructive-foreground",
          dot && "size-2 p-0",
          className,
        )}
        style={{ ...(color ? { backgroundColor: color } : null), ...style }}
        {...props}
      >
        {dot ? null : shown}
      </span>
    ) : null;
  }

  return (
    <span
      ref={ref}
      className={cn("relative inline-flex", className)}
      {...props}
    >
      {children}
      {visible ? (
        <span
          className={cn(
            // pointer-events-none: the count is decoration painted OVER the
            // child, and `offset` routinely pulls it across the child's middle
            // (PromptChangeIndicator uses [-2, 12] to dodge the prompt row's
            // overflow clipping). Without this it swallows the clicks meant for
            // the child, and worse, only once the count is wide enough to cover
            // it -- a one-digit badge left the icon's centre reachable, two
            // digits masked 85% of it and the button went dead.
            "pointer-events-none absolute -right-1 -top-1 inline-flex items-center justify-center rounded-full bg-destructive px-1.5 text-xs text-destructive-foreground",
            dot && "size-2 p-0",
          )}
          style={{
            ...(color ? { backgroundColor: color } : null),
            // antd's `offset` is [x, y] in px, applied to the count.
            ...(Array.isArray(offset)
              ? { transform: `translate(${offset[0]}px, ${offset[1]}px)` }
              : null),
            ...style,
          }}
        >
          {dot ? null : shown}
        </span>
      ) : null}
    </span>
  );
});

const Card = Object.assign(CardBase, { Meta: CardMeta });
const Tabs = Object.assign(TabsBase, { TabPane });
const Tree = Object.assign(TreeBase, { DirectoryTree });
const Steps = Object.assign(StepsBase, { Step });
const List = Object.assign(ListBase, {
  Item: Object.assign(ListItem, { Meta: ListItemMeta }),
});
const Layout = Object.assign(LayoutBase, {
  Header,
  Content,
  Sider,
  Footer,
});
const Upload = Object.assign(UploadBase, { Dragger, LIST_IGNORE });
const Menu = Object.assign(MenuBase, {
  Item: MenuItem,
  ItemGroup: MenuItemGroup,
});
const Descriptions = Object.assign(DescriptionsBase, {
  Item: DescriptionsItem,
});
const FloatButton = Object.assign(FloatButtonBase, {
  Group: FloatButtonGroup,
});

export {
  Badge,
  Card,
  Descriptions,
  Drawer,
  FloatButton,
  Layout,
  List,
  Menu,
  Pagination,
  Result,
  Segmented,
  Skeleton,
  Statistic,
  Steps,
  Table,
  Tabs,
  Transfer,
  Tree,
  Upload,
};
