import { CircleCheck, CircleX, Upload as UploadIcon } from "lucide-react";
import * as React from "react";
import { DataTable } from "@/components/data-table/DataTable";
import { Button } from "@/components/ui/antd-button";
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
const Table = DataTable;
Table.Column = function Column() {
  return null;
};

/** antd `<Card title extra bordered>`. */
const Card = React.forwardRef(function Card(
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
    <ShadcnCard
      ref={ref}
      className={cn(!bordered && "border-0 shadow-none", className)}
      {...props}
    >
      {title || extra ? (
        <CardHeader
          className={cn(
            "flex-row items-center justify-between",
            size === "small" && "p-3",
          )}
        >
          {title ? (
            <CardTitle className="text-base">{title}</CardTitle>
          ) : (
            <span />
          )}
          {extra}
        </CardHeader>
      ) : null}
      <CardContent className={cn(size === "small" && "p-3 pt-0")}>
        {children}
      </CardContent>
    </ShadcnCard>
  );
});

/**
 * antd `<Tabs items activeKey onChange>`. Also supports the legacy
 * `<Tabs.TabPane>` children form.
 */
const Tabs = React.forwardRef(function Tabs(
  {
    items,
    activeKey,
    defaultActiveKey,
    onChange,
    tabBarExtraContent,
    type,
    className,
    children,
    ...props
  },
  ref,
) {
  const panes =
    items ??
    React.Children.toArray(children)
      .filter(Boolean)
      .map((c) => ({
        key: c.props?.tabKey ?? c.props?.key,
        label: c.props?.tab,
        children: c.props?.children,
      }));

  const first = panes[0]?.key;

  return (
    <ShadcnTabs
      ref={ref}
      // Radix treats a present-but-undefined `value` as controlled, which
      // freezes the tabs. Pass EITHER value (antd's controlled activeKey) OR
      // defaultValue (uncontrolled), never both.
      {...(activeKey != null
        ? { value: String(activeKey) }
        : { defaultValue: String(defaultActiveKey ?? first ?? "") })}
      onValueChange={(v) => onChange?.(v)}
      className={className}
      {...props}
    >
      <div className="flex items-center justify-between">
        <TabsList>
          {panes.map((p) => (
            <TabsTrigger
              key={String(p.key)}
              value={String(p.key)}
              disabled={p.disabled}
            >
              {p.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabBarExtraContent}
      </div>
      {panes.map((p) => (
        <TabsContent key={String(p.key)} value={String(p.key)}>
          {p.children}
        </TabsContent>
      ))}
    </ShadcnTabs>
  );
});

Tabs.TabPane = function TabPane({ children }) {
  return children ?? null;
};

// Written out so Tailwind sees the class names statically.
const LIST_GRID_COLS = {
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
const List = React.forwardRef(function List(
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
  const isGrid = Boolean(cols);

  return (
    <div
      ref={ref}
      className={cn(
        isGrid ? "grid" : "divide-y",
        isGrid && LIST_GRID_COLS[cols],
        className,
      )}
      style={isGrid && grid?.gutter ? { gap: grid.gutter } : undefined}
      {...props}
    >
      {header ? <div className="py-2 font-medium">{header}</div> : null}
      {dataSource.length ? (
        dataSource.map((item, i) => (
          <div key={i} className={isGrid ? undefined : "py-2"}>
            {renderItem?.(item, i)}
          </div>
        ))
      ) : (
        <div className="py-6 text-center text-muted-foreground">
          {locale?.emptyText ?? "No data"}
        </div>
      )}
      {footer ? <div className="py-2">{footer}</div> : null}
    </div>
  );
});

List.Item = function ListItem({ actions, children, className, ...props }) {
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
};
List.Item.Meta = function ListItemMeta({ avatar, title, description }) {
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
};

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
const SiderRegistryContext = React.createContext(null);

const Layout = React.forwardRef(function Layout(
  { className, hasSider, children, ...props },
  ref,
) {
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
});

Layout.Header = function Header({ className, ...p }) {
  return <header className={cn("flex items-center", className)} {...p} />;
};
Layout.Content = function Content({ className, ...p }) {
  return <main className={cn("min-h-0 flex-auto", className)} {...p} />;
};
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
Layout.Sider = function Sider({
  className,
  width = 200,
  collapsed,
  collapsedWidth = 80,
  collapsible,
  trigger,
  breakpoint,
  onCollapse,
  style,
  ...p
}) {
  // Tell the nearest ancestor Layout to lay out as a row (antd's hasSider).
  const register = React.useContext(SiderRegistryContext);
  React.useEffect(() => register?.(), [register]);

  return (
    <aside
      className={cn("shrink-0 transition-[width] duration-200", className)}
      style={{ width: collapsed ? collapsedWidth : width, ...style }}
      data-collapsed={collapsed ? "true" : undefined}
      {...p}
    />
  );
};
Layout.Footer = function Footer({ className, ...p }) {
  return <footer className={className} {...p} />;
};

/** antd `<Upload beforeUpload customRequest>` over a hidden file input. */
const Upload = React.forwardRef(function Upload(
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
  const inputRef = React.useRef(null);

  const handleFiles = async (files) => {
    for (const file of files) {
      // antd aborts the upload when beforeUpload returns false.
      const proceed = beforeUpload ? await beforeUpload(file, files) : true;
      if (proceed === false) {
        continue;
      }
      customRequest?.({
        file,
        onSuccess: (body) =>
          onChange?.({
            file: { status: "done", response: body, originFileObj: file },
          }),
        onError: (err) =>
          onChange?.({
            file: { status: "error", error: err, originFileObj: file },
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
    <span ref={ref} className={cn("inline-block", className)} {...props}>
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
      >
        {children ?? (
          <Button icon={<UploadIcon className="size-4" />}>Upload</Button>
        )}
      </span>
    </span>
  );
});

Upload.Dragger = Upload;

/** antd `<Result status title subTitle extra>`. */
const Result = React.forwardRef(function Result(
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
      {title ? <div className="text-lg font-semibold">{title}</div> : null}
      {subTitle ? (
        <div className="text-sm text-muted-foreground">{subTitle}</div>
      ) : null}
      {extra}
      {children}
    </div>
  );
});

/** antd `<Drawer open onClose placement>` → shadcn Sheet. */
const Drawer = React.forwardRef(function Drawer(
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
const Segmented = React.forwardRef(function Segmented(
  { options = [], value, onChange, className, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn("inline-flex gap-1 rounded-md bg-muted p-1", className)}
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
              "rounded px-3 py-1 text-sm",
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
});

/** antd `<Menu items onClick>` — a simple vertical list. */
const Menu = React.forwardRef(function Menu(
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
          onClick={() => onClick?.({ key: item.key })}
          className={cn(
            "flex items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent",
            selectedKeys.includes(item.key) && "bg-accent font-medium",
          )}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </nav>
  );
});
Menu.Item = function MenuItem({ children }) {
  return children ?? null;
};

/** antd `<Skeleton active paragraph />`. */
const Skeleton = React.forwardRef(function Skeleton(
  { active, paragraph, title = true, className, ...props },
  ref,
) {
  const rows = paragraph?.rows ?? 3;
  return (
    <div ref={ref} className={cn("space-y-2", className)} {...props}>
      {title ? <ShadcnSkeleton className="h-5 w-1/3" /> : null}
      {Array.from({ length: rows }).map((_, i) => (
        <ShadcnSkeleton key={i} className="h-4 w-full" />
      ))}
    </div>
  );
});

/** antd `<Steps current items>`. */
const Steps = React.forwardRef(function Steps(
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
const Pagination = React.forwardRef(function Pagination(
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
});

/** antd `<Tree treeData>` — a shallow nested list; no call-site drags nodes. */
const Tree = React.forwardRef(function Tree(
  { treeData = [], onSelect, className, ...props },
  ref,
) {
  const renderNodes = (nodes, depth = 0) =>
    nodes.map((n) => (
      <div key={String(n.key)} style={{ paddingLeft: depth * 12 }}>
        <button
          type="button"
          className="rounded px-1 py-0.5 text-left text-sm hover:bg-accent"
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
const Descriptions = React.forwardRef(function Descriptions(
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
                <dt className="text-sm text-muted-foreground">{item.label}</dt>
                <dd className="text-sm">{item.children}</dd>
              </div>
            ))
          : children}
      </dl>
    </div>
  );
});

Descriptions.Item = function DescriptionsItem({ label, children }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
};

/** antd `<Statistic title value prefix suffix precision />`. */
const Statistic = React.forwardRef(function Statistic(
  { title, value, precision, prefix, suffix, valueStyle, className, ...props },
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
});

/** antd `<FloatButton icon onClick tooltip />`. */
const FloatButton = React.forwardRef(function FloatButton(
  { icon, onClick, tooltip, type, className, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      title={tooltip}
      onClick={onClick}
      className={cn(
        "fixed bottom-6 right-6 z-50 flex size-11 items-center justify-center rounded-full shadow-lg",
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
});
FloatButton.Group = function FloatButtonGroup({ children }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {children}
    </div>
  );
};

/**
 * antd `<Transfer>` — dual list with move-between controls. Kept minimal: the
 * cloud call-sites use dataSource/targetKeys/onChange only.
 */
const Transfer = React.forwardRef(function Transfer(
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
  const move = (key, toTarget) => {
    const next = toTarget
      ? [...targetKeys, key]
      : targetKeys.filter((k) => k !== key);
    onChange?.(next, toTarget ? "right" : "left", [key]);
  };

  const column = (title, entries, toTarget) => (
    <div className="flex-1 rounded-md border">
      <div className="border-b px-3 py-2 text-sm font-medium">{title}</div>
      <div className="max-h-64 divide-y overflow-auto">
        {entries.map((item) => (
          <button
            key={String(item.key)}
            type="button"
            className="block w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
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
});

/**
 * antd `<Badge count dot status>` — a small counter/dot overlaid on its child.
 * Distinct from shadcn's `Badge` (a pill label), which is what antd calls Tag.
 */
const Badge = React.forwardRef(function Badge(
  {
    count,
    dot,
    status,
    color,
    overflowCount = 99,
    showZero,
    offset,
    className,
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
        style={color ? { backgroundColor: color } : undefined}
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
          style={color ? { backgroundColor: color } : undefined}
        >
          {dot ? null : shown}
        </span>
      ) : null}
    </span>
  );
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
