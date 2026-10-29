/*
 * The Lucide glyph for each destination and shared role in the v1 designs,
 * so a page asks for `ACTION_ICONS.delete`, not `Trash2`, and a swap is a
 * one-line change here. Page-specific glyphs (viewer zoom, chart types) are
 * imported from lucide-react directly.
 *
 * Canonical names only: lucide-react 1.x keeps old names such as `Loader2`
 * and `FileCheck2` as aliases, and lint:v1 bans the ones the designs and v0
 * use. Lucide is the only icon library v1 may import.
 */
import {
  ArrowLeft,
  Bell,
  Bot,
  Boxes,
  Braces,
  BrainCircuit,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  CircleAlert,
  CircleCheck,
  Copy,
  Database,
  Download,
  EllipsisVertical,
  ExternalLink,
  Eye,
  FileCheckCorner,
  FileText,
  FileType,
  Info,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  ListFilter,
  LoaderCircle,
  LogOut,
  type LucideIcon,
  PanelLeft,
  Pencil,
  Play,
  Plug,
  Plus,
  RefreshCw,
  Rocket,
  ScanText,
  ScrollText,
  Search,
  Settings,
  Share2,
  SlidersHorizontal,
  Star,
  Trash2,
  TriangleAlert,
  Upload,
  Users,
  Workflow,
  X,
  Zap,
} from "lucide-react";

/** Left-rail destinations (dev spec §9, node 1192:226), in rail order. */
export const RAIL_ICONS = {
  "prompt-studio": ScanText,
  "agentic-studio": Bot,
  workflows: Workflow,
  "api-deployments": Braces,
  "etl-pipelines": CalendarClock,
  "task-pipelines": Zap,
  dashboard: LayoutDashboard,
  logs: ScrollText,
  "human-review": FileCheckCorner,
  llms: BrainCircuit,
  "vector-dbs": Database,
  embedding: Boxes,
  "text-extractor": FileType,
  connectors: Plug,
  platform: SlidersHorizontal,
} as const satisfies Record<string, LucideIcon>;

export type RailDestination = keyof typeof RAIL_ICONS;

/** Top bar and head row (node 1195:231). */
export const SHELL_ICONS = {
  productSwitcher: LayoutGrid,
  search: Search,
  notifications: Bell,
  orgSwitcher: ChevronsUpDown,
  accountMenu: ChevronDown,
  railToggle: PanelLeft,
  back: ArrowLeft,
  signOut: LogOut,
} as const satisfies Record<string, LucideIcon>;

/** The Platform flyout's four drawn rows ("Menu · Platform"). */
export const PLATFORM_MENU_ICONS = {
  general: SlidersHorizontal,
  access: Users,
  apiKeys: KeyRound,
  defaults: Star,
} as const satisfies Record<string, LucideIcon>;

/** Actions drawn on ten or more build pages. */
export const ACTION_ICONS = {
  more: EllipsisVertical,
  add: Plus,
  edit: Pencil,
  delete: Trash2,
  copy: Copy,
  download: Download,
  upload: Upload,
  refresh: RefreshCw,
  share: Share2,
  openExternal: ExternalLink,
  settings: Settings,
  close: X,
  confirm: Check,
  expand: ChevronDown,
  next: ChevronRight,
  back: ArrowLeft,
  filter: ListFilter,
  run: Play,
  view: Eye,
  deploy: Rocket,
  apiKeys: KeyRound,
  document: FileText,
} as const satisfies Record<string, LucideIcon>;

/** The status set every screen ships (dev spec §8). */
export const STATUS_ICONS = {
  success: CircleCheck,
  warning: TriangleAlert,
  error: CircleAlert,
  info: Info,
  loading: LoaderCircle,
} as const satisfies Record<string, LucideIcon>;

/** What an adapter or connector is; picks the fallback glyph for its logo. */
export type ProviderCategory =
  | "llm"
  | "embedding"
  | "vector-db"
  | "text-extractor"
  | "connector";

/** A provider with no mark and no usable icon shows its category's rail glyph. */
export const CATEGORY_ICONS = {
  llm: RAIL_ICONS.llms,
  embedding: RAIL_ICONS.embedding,
  "vector-db": RAIL_ICONS["vector-dbs"],
  "text-extractor": RAIL_ICONS["text-extractor"],
  connector: RAIL_ICONS.connectors,
} as const satisfies Record<ProviderCategory, LucideIcon>;
