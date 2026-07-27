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
      value={activeKey != null ? String(activeKey) : undefined}
      defaultValue={String(defaultActiveKey ?? first ?? "")}
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

/** antd `<List dataSource renderItem>`. */
const List = React.forwardRef(function List(
  { dataSource = [], renderItem, header, footer, className, locale, ...props },
  ref,
) {
  return (
    <div ref={ref} className={cn("divide-y", className)} {...props}>
      {header ? <div className="py-2 font-medium">{header}</div> : null}
      {dataSource.length ? (
        dataSource.map((item, i) => (
          <div key={i} className="py-2">
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

/** antd `<Layout>` and its slots — plain flex containers. */
const Layout = React.forwardRef(function Layout(
  { className, children, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn("flex min-h-0 flex-col", className)}
      {...props}
    >
      {children}
    </div>
  );
});
Layout.Header = function Header({ className, ...p }) {
  return <header className={cn("flex items-center", className)} {...p} />;
};
Layout.Content = function Content({ className, ...p }) {
  return <main className={cn("min-h-0 flex-1", className)} {...p} />;
};
Layout.Sider = function Sider({ className, width, ...p }) {
  return (
    <aside className={cn("shrink-0", className)} style={{ width }} {...p} />
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

export {
  Card,
  Drawer,
  Layout,
  List,
  Menu,
  Pagination,
  Result,
  Segmented,
  Skeleton,
  Steps,
  Table,
  Tabs,
  Tree,
  Upload,
};
