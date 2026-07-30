import { CircleCheck, CircleX, Upload as UploadIcon } from "lucide-react";
import * as React from "react";
import { DataTable } from "@/components/data-table/DataTable";
import {
  CardContent,
  CardHeader,
  CardTitle,
  Card as ShadcnCard,
} from "@/components/ui/card";
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
}

interface CardProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title?: React.ReactNode;
  /** Rendered at the top-right of the header. */
  extra?: React.ReactNode;
  bordered?: boolean;
  size?: SizeToken;
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
  accept?: string;
  multiple?: boolean;
  showUploadList?: boolean;
  fileList?: UploadFile[];
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
}

interface MenuProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onClick"> {
  items?: KeyedItem[];
  selectedKeys?: string[];
  onClick?: (info: { key: string }) => void;
  mode?: "vertical" | "horizontal" | "inline";
}

interface SkeletonProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  active?: boolean;
  /** `true`, or `{ rows }` for an explicit line count. */
  paragraph?: boolean | { rows?: number };
  title?: boolean;
}

interface StepsProps extends React.HTMLAttributes<HTMLOListElement> {
  current?: number;
  items?: Array<{ title?: React.ReactNode; description?: React.ReactNode }>;
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
  children?: TreeNode[];
}

interface TreeProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onSelect"> {
  treeData?: TreeNode[];
  onSelect?: (keys: string[], info: { node: TreeNode }) => void;
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
      className={cn("ant-card", !bordered && "border-0 shadow-none", className)}
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
          children?: React.ReactNode;
          disabled?: boolean;
        }> => React.isValidElement(c),
      )
      .map((c) => ({
        key: c.props.tabKey ?? c.props.key,
        label: c.props.tab,
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
              disabled={p.disabled}
              className={cn(
                type !== "card" &&
                  // Underline the active tab; keep the label tinted like antd.
                  "rounded-none border-b-2 border-transparent bg-transparent px-0 font-normal shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:shadow-none",
                /*
                 * Symmetric padding, not `pb-2`. Bottom-heavy padding puts the
                 * LABEL above the centre of its own 36px box, so `align-items:
                 * center` on the toolbar lined up the boxes while the text sat
                 * 5.6px above the file name beside it. antd pads 12px evenly
                 * for a 22px label box.
                 */
                type !== "card" && "py-3",
              )}
            >
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

function ListItem({
  actions,
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { actions?: React.ReactNode[] }) {
  return (
    <div
      className={cn("flex items-center justify-between gap-2", className)}
      {...props}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {actions?.length ? (
        <div className="flex items-center gap-2">{actions}</div>
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
 * Two behaviours here are load-bearing, and both caused real breakage when
 * they were missing:
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
            "flex min-h-0 flex-auto",
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

/** antd `<Upload beforeUpload customRequest>` over a hidden file input. */
const UploadBase = React.forwardRef<HTMLElement, UploadProps>(function Upload(
  {
    beforeUpload,
    customRequest,
    onChange,
    accept,
    multiple,
    showUploadList,
    fileList,
    disabled,
    children,
    className,
    ...props
  },
  ref,
) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      // antd aborts the upload when beforeUpload returns false.
      const proceed = beforeUpload ? await beforeUpload(file, files) : true;
      if (proceed === false) {
        continue;
      }
      customRequest?.({
        file,
        onSuccess: (body?: unknown) =>
          onChange?.({
            file: { status: "done", response: body, originFileObj: file },
            fileList: fileList ?? [],
          }),
        onError: (err?: unknown) =>
          onChange?.({
            file: { status: "error", response: err, originFileObj: file },
            fileList: fileList ?? [],
          }),
      });
      if (!customRequest) {
        onChange?.({
          file: { status: "done", originFileObj: file },
          fileList: files,
        });
      }
    }
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
        onChange={(e) => handleFiles(Array.from(e.target.files ?? []))}
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
    className,
    children,
    ...props
  },
  ref,
) {
  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose?.()}>
      <SheetContent
        ref={ref}
        side={placement}
        style={{ maxWidth: width }}
        className={className}
        {...props}
      >
        {title ? (
          <SheetHeader>
            <SheetTitle>{title}</SheetTitle>
          </SheetHeader>
        ) : null}
        {children}
      </SheetContent>
    </Sheet>
  );
});

/** antd `<Segmented options value onChange>`. */
const Segmented = React.forwardRef<HTMLDivElement, SegmentedProps>(
  function Segmented(
    { options = [], value, onChange, className, ...props },
    ref,
  ) {
    return (
      <div
        ref={ref}
        className={cn("inline-flex gap-1 rounded-md bg-muted p-1", className)}
        data-segmented=""
        {...props}
      >
        {options.map((o) => {
          const val = typeof o === "object" ? o.value : o;
          const label = typeof o === "object" ? o.label : o;
          return (
            <button
              key={String(val)}
              type="button"
              onClick={() => onChange?.(val)}
              className={cn(
                "ant-segmented-item cursor-pointer rounded px-3 py-1 text-sm disabled:cursor-not-allowed",
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
  { items = [], selectedKeys = [], onClick, mode, className, ...props },
  ref,
) {
  return (
    <nav ref={ref} className={cn("flex flex-col gap-1", className)} {...props}>
      {items.filter(Boolean).map((item) => (
        <button
          key={String(item.key)}
          type="button"
          disabled={item.disabled}
          onClick={() => onClick?.({ key: String(item.key) })}
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

/** antd `<Skeleton active paragraph />`. */
const Skeleton = React.forwardRef<HTMLDivElement, SkeletonProps>(
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

/** antd `<Steps current items>`. */
const Steps = React.forwardRef<HTMLOListElement, StepsProps>(function Steps(
  { current = 0, items = [], className, ...props },
  ref,
) {
  return (
    <ol
      ref={ref}
      className={cn("flex items-center gap-4", className)}
      {...props}
    >
      {items.map((item, i) => (
        <li key={String(item.title ?? i)} className="flex items-center gap-2">
          <span
            className={cn(
              "flex size-6 items-center justify-center rounded-full text-xs",
              i <= current
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground",
            )}
          >
            {i + 1}
          </span>
          <span className={cn("text-sm", i === current && "font-medium")}>
            {item.title}
          </span>
        </li>
      ))}
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
const Tree = React.forwardRef<HTMLDivElement, TreeProps>(function Tree(
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
 * antd `<Descriptions>` — a label/value grid. Only cloud plugins use it, but it
 * lives here per D9 so both repos share one implementation.
 */
const DescriptionsBase = React.forwardRef<HTMLDivElement, DescriptionsProps>(
  function Descriptions(
    { title, items, column = 3, bordered, className, children, ...props },
    ref,
  ) {
    return (
      <div ref={ref} className={cn("w-full", className)} {...props}>
        {title ? <div className="mb-2 font-medium">{title}</div> : null}
        <dl
          className={cn(
            "grid gap-x-4 gap-y-2",
            bordered && "rounded-md border p-3",
          )}
          style={{ gridTemplateColumns: `repeat(${column}, minmax(0, 1fr))` }}
        >
          {items
            ? items.map((item) => (
                <div key={String(item.key ?? item.label)}>
                  <dt className="text-sm text-muted-foreground">
                    {item.label}
                  </dt>
                  <dd className="text-sm">{item.children}</dd>
                </div>
              ))
            : children}
        </dl>
      </div>
    );
  },
);

function DescriptionsItem({
  label,
  children,
}: {
  label?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
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
 * antd `<Transfer>` — dual list with move-between controls. Kept minimal: the
 * cloud call-sites use dataSource/targetKeys/onChange only.
 */
const Transfer = React.forwardRef<HTMLDivElement, TransferProps>(
  function Transfer(
    {
      dataSource = [],
      targetKeys = [],
      onChange,
      render,
      titles = ["Source", "Target"],
      className,
      ...props
    },
    ref,
  ) {
    const inTarget = new Set(targetKeys);
    const move = (key: string, toTarget: boolean) => {
      const next = toTarget
        ? [...targetKeys, key]
        : targetKeys.filter((k) => k !== key);
      onChange?.(next, toTarget ? "right" : "left", [key]);
    };

    const column = (
      title: React.ReactNode,
      entries: TransferItem[],
      toTarget: boolean,
    ) => (
      <div className="flex-1 rounded-md border">
        <div className="border-b px-3 py-2 text-sm font-medium">{title}</div>
        <div className="max-h-64 divide-y divide-border overflow-auto">
          {entries.map((item) => (
            <button
              key={String(item.key)}
              type="button"
              className="block w-full cursor-pointer px-3 py-1.5 text-left text-sm hover:bg-accent"
              onClick={() => move(item.key, toTarget)}
            >
              {render ? render(item) : item.title}
            </button>
          ))}
        </div>
      </div>
    );

    return (
      <div
        ref={ref}
        className={cn("flex items-start gap-3", className)}
        {...props}
      >
        {column(
          titles[0],
          dataSource.filter((d) => !inTarget.has(d.key)),
          true,
        )}
        {column(
          titles[1],
          dataSource.filter((d) => inTarget.has(d.key)),
          false,
        )}
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
            "absolute -right-1 -top-1 inline-flex items-center justify-center rounded-full bg-destructive px-1.5 text-xs text-destructive-foreground",
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
const List = Object.assign(ListBase, {
  Item: Object.assign(ListItem, { Meta: ListItemMeta }),
});
const Layout = Object.assign(LayoutBase, {
  Header,
  Content,
  Sider,
  Footer,
});
const Upload = Object.assign(UploadBase, { Dragger });
const Menu = Object.assign(MenuBase, { Item: MenuItem });
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
