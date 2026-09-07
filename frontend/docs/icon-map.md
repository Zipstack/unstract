# antd icons → lucide-react (P1-01)

**Complete mapping — all 116 icons** used across both repos before the
migration: **87** distinct icons in OSS (`unstract`) and **87**
in the enterprise plugins (`unstract-cloud`), overlapping to 116 unique.

Every target name was verified to exist in the installed `lucide-react` build
before the mapping was applied. Counts below are **import sites** in the
pre-migration tree (`unstract@023b14021`, `unstract-cloud@main`).

## Sizing / colour convention

antd icons inherit `font-size` and `color`; lucide icons take `size`/`className`.
Conversions use Tailwind classes so rendered size is unchanged:

| antd context | lucide replacement |
|---|---|
| default inline icon (14px) | `className="size-3.5"` |
| icon inside a `Button` | `className="size-4"` |
| explicit `style={{ fontSize: N }}` | `className="size-[Npx]"` |
| colour via `style={{ color }}` | keep the inline style, or use `text-*` |

Both libraries drive colour from `currentColor`, so inherited colour needs no change.

## ⚠ Mappings that are NOT exact — these need a human eye

27 of 116 pairs are approximations. lucide is not a
drop-in replacement for antd's icon set: it has **no filled variants at all**,
and it dropped brand icons.

| antd | lucide | OSS | Cloud | Why it differs |
|---|---|---|---|---|
| `ArrowsAltOutlined` | `Move` | 1 | 2 | antd's is a 4-way expand arrow. `Move` is closest; use `Maximize2` if the intent was 'expand'.
| `AuditOutlined` | `ClipboardCheck` | 0 | 1 | No direct match; `ClipboardCheck` conveys the review/audit sense.
| `CaretDownOutlined` | `ChevronDown` | 1 | 0 | Solid triangle → thin chevron. Also matches the shadcn/Radix idiom used elsewhere.
| `CaretRightOutlined` | `ChevronRight` | 1 | 0 | Solid triangle → thin chevron.
| `CheckCircleFilled` | `CircleCheck` | 5 | 7 | lucide has **no filled variants** — renders as an outline, visually lighter than antd's solid glyph. Add `fill-current` where the solid weight carried meaning.
| `ClearOutlined` | `Eraser` | 2 | 0 | → `Eraser`.
| `CloseCircleFilled` | `CircleX` | 6 | 3 | Same filled→outline caveat.
| `CompressOutlined` | `Shrink` | 0 | 1 | → `Shrink`.
| `ContainerOutlined` | `Container` | 0 | 1 | antd's is a document tray; `Container` is a shipping container. Different metaphor, similar role.
| `DashboardOutlined` | `Gauge` | 1 | 0 | antd's is a speedometer; `Gauge` is the nearest equivalent.
| `DiffOutlined` | `GitCompare` | 1 | 0 | → `GitCompare`; carries a VCS connotation antd's did not.
| `ExclamationCircleFilled` | `CircleAlert` | 2 | 4 | Same filled→outline caveat.
| `ExclamationOutlined` | `TriangleAlert` | 0 | 1 | Bare exclamation → `TriangleAlert` (adds a triangle the original lacked).
| `ExportOutlined` | `ExternalLink` | 1 | 4 | antd's implies data export; `ExternalLink` implies navigation. Closest available.
| `FieldTimeOutlined` | `Timer` | 0 | 1 | No direct match; `Timer` is closest.
| `FilePdfOutlined` | `FileText` | 2 | 3 | No PDF-specific glyph in lucide — falls back to generic `FileText`, losing the format hint.
| `InfoCircleFilled` | `Info` | 4 | 1 | Same filled→outline caveat.
| `MergeCellsOutlined` | `Merge` | 1 | 0 | Table-cell merge → generic `Merge`.
| `MoreOutlined` | `EllipsisVertical` | 5 | 0 | antd's is **vertical** (⋮). Plain `Ellipsis` is horizontal, so `EllipsisVertical` is the correct target.
| `PlayCircleFilled` | `CirclePlay` | 4 | 0 | Same filled→outline caveat.
| `RotateLeftOutlined` | `RotateCcw` | 0 | 1 | → `RotateCcw` (counter-clockwise).
| `ScheduleOutlined` | `CalendarClock` | 2 | 0 | antd's is a clipboard-with-check; no direct match. `CalendarClock` fits the scheduling context. Alternative: `ClipboardCheck`.
| `SlackOutlined` | `MessagesSquare` | 1 | 2 | **lucide dropped brand icons** — the Slack mark is gone. `MessagesSquare` is a generic stand-in.
| `StarFilled` | `Star` | 0 | 1 | Same filled→outline caveat; `Star` is stroked.
| `ThunderboltFilled` | `Zap` | 0 | 1 | Same filled→outline caveat.
| `UserSwitchOutlined` | `UserRoundCog` | 1 | 1 | → `UserRoundCog`; antd's implies switching users, lucide's implies configuring one.
| `WarningFilled` | `TriangleAlert` | 0 | 3 | Same filled→outline caveat.

### The filled-variant problem

lucide has no filled equivalents, so all 8 `*Filled` icons render lighter than
before. Where the solid weight carried meaning (status indicators especially),
use fill explicitly:

```jsx
// antd:   <CheckCircleFilled style={{ color: "#52c41a" }} />
// lucide: solid look via fill + stroke on the same token
<CircleCheck className="size-3.5 fill-success text-white" />
```

## Exact mappings

89 pairs where the glyph and meaning both carry over.

| antd | lucide | OSS | Cloud |
|---|---|---|---|
| `ApiOutlined` | `Plug` | 2 | 1 |
| `AppstoreOutlined` | `LayoutGrid` | 1 | 0 |
| `ArrowDownOutlined` | `ArrowDown` | 2 | 0 |
| `ArrowLeftOutlined` | `ArrowLeft` | 10 | 10 |
| `ArrowRightOutlined` | `ArrowRight` | 0 | 2 |
| `ArrowUpOutlined` | `ArrowUp` | 1 | 0 |
| `BarChartOutlined` | `ChartColumn` | 1 | 0 |
| `BranchesOutlined` | `GitBranch` | 2 | 2 |
| `BugOutlined` | `Bug` | 1 | 0 |
| `BulbOutlined` | `Lightbulb` | 0 | 2 |
| `CalendarOutlined` | `Calendar` | 2 | 2 |
| `CheckCircleOutlined` | `CircleCheck` | 8 | 6 |
| `CheckOutlined` | `Check` | 1 | 2 |
| `ClockCircleOutlined` | `Clock` | 4 | 5 |
| `CloseCircleOutlined` | `CircleX` | 2 | 1 |
| `CloseOutlined` | `X` | 2 | 6 |
| `CloudDownloadOutlined` | `CloudDownload` | 3 | 1 |
| `CloudUploadOutlined` | `CloudUpload` | 1 | 1 |
| `CodeOutlined` | `Code` | 2 | 1 |
| `CopyOutlined` | `Copy` | 11 | 13 |
| `CreditCardOutlined` | `CreditCard` | 1 | 2 |
| `CrownOutlined` | `Crown` | 0 | 2 |
| `DatabaseOutlined` | `Database` | 2 | 1 |
| `DeleteOutlined` | `Trash2` | 20 | 19 |
| `DollarCircleOutlined` | `CircleDollarSign` | 0 | 1 |
| `DollarOutlined` | `DollarSign` | 1 | 1 |
| `DoubleRightOutlined` | `ChevronsRight` | 1 | 0 |
| `DownOutlined` | `ChevronDown` | 3 | 2 |
| `DownloadOutlined` | `Download` | 1 | 5 |
| `EditOutlined` | `Pencil` | 14 | 10 |
| `EllipsisOutlined` | `Ellipsis` | 2 | 1 |
| `ExclamationCircleOutlined` | `CircleAlert` | 1 | 5 |
| `ExpandOutlined` | `Expand` | 1 | 1 |
| `ExperimentOutlined` | `FlaskConical` | 0 | 3 |
| `EyeInvisibleOutlined` | `EyeOff` | 0 | 3 |
| `EyeOutlined` | `Eye` | 2 | 9 |
| `FileAddOutlined` | `FilePlus` | 0 | 1 |
| `FileDoneOutlined` | `FileCheck` | 0 | 1 |
| `FileExclamationOutlined` | `FileWarning` | 1 | 0 |
| `FileProtectOutlined` | `FileCheck` | 1 | 0 |
| `FileSearchOutlined` | `FileSearch` | 3 | 2 |
| `FileTextOutlined` | `FileText` | 5 | 10 |
| `FilterOutlined` | `Filter` | 4 | 0 |
| `FolderOpenOutlined` | `FolderOpen` | 0 | 1 |
| `ForkOutlined` | `GitFork` | 1 | 0 |
| `FullscreenExitOutlined` | `Minimize` | 1 | 0 |
| `FullscreenOutlined` | `Maximize` | 1 | 1 |
| `GiftOutlined` | `Gift` | 0 | 1 |
| `HistoryOutlined` | `History` | 3 | 4 |
| `HomeOutlined` | `House` | 0 | 1 |
| `HourglassOutlined` | `Hourglass` | 2 | 0 |
| `InboxOutlined` | `Inbox` | 1 | 5 |
| `InfoCircleOutlined` | `Info` | 8 | 13 |
| `KeyOutlined` | `Key` | 2 | 0 |
| `LeftOutlined` | `ChevronLeft` | 2 | 1 |
| `LineChartOutlined` | `ChartLine` | 0 | 1 |
| `LinkOutlined` | `Link` | 0 | 5 |
| `LoadingOutlined` | `LoaderCircle` | 2 | 4 |
| `LockOutlined` | `Lock` | 0 | 1 |
| `LoginOutlined` | `LogIn` | 1 | 1 |
| `LogoutOutlined` | `LogOut` | 1 | 2 |
| `MailOutlined` | `Mail` | 1 | 0 |
| `MenuOutlined` | `Menu` | 0 | 1 |
| `MessageOutlined` | `MessageSquare` | 1 | 2 |
| `MinusOutlined` | `Minus` | 1 | 0 |
| `NotificationOutlined` | `Bell` | 2 | 0 |
| `PlayCircleOutlined` | `CirclePlay` | 6 | 4 |
| `PlusOutlined` | `Plus` | 13 | 12 |
| `QuestionCircleOutlined` | `CircleHelp` | 8 | 2 |
| `ReloadOutlined` | `RotateCw` | 8 | 11 |
| `RightCircleOutlined` | `CircleChevronRight` | 0 | 2 |
| `RightOutlined` | `ChevronRight` | 2 | 1 |
| `RocketOutlined` | `Rocket` | 2 | 0 |
| `SaveOutlined` | `Save` | 0 | 6 |
| `SearchOutlined` | `Search` | 8 | 5 |
| `SendOutlined` | `Send` | 0 | 1 |
| `SettingOutlined` | `Settings` | 4 | 3 |
| `ShareAltOutlined` | `Share2` | 3 | 5 |
| `SwapOutlined` | `ArrowLeftRight` | 0 | 3 |
| `SyncOutlined` | `RefreshCw` | 6 | 0 |
| `TableOutlined` | `Table` | 2 | 2 |
| `TagOutlined` | `Tag` | 0 | 1 |
| `TeamOutlined` | `Users` | 2 | 0 |
| `ThunderboltOutlined` | `Zap` | 2 | 4 |
| `UnorderedListOutlined` | `List` | 2 | 1 |
| `UpOutlined` | `ChevronUp` | 2 | 0 |
| `UploadOutlined` | `Upload` | 2 | 6 |
| `UserOutlined` | `User` | 8 | 5 |
| `WarningOutlined` | `TriangleAlert` | 2 | 6 |

## Import forms handled

- Named imports (`import {{ X }} from "@ant-design/icons"`) — the only form used.
- **Multi-line import blocks**, which the first enumeration pass missed: the
  original single-line regex found only 43 of 87 OSS icons. Anything scoping a
  future sweep should use a `re.S` pattern.
- Files with **two separate** icon import statements (e.g. `ReviewHeader.jsx`).
- No deep imports (`@ant-design/icons/...`) and no default-import form exist.

## Name collisions the rename introduced

A lucide icon can collide with a same-named component in scope. Nine cases were
found; each is fixed by aliasing the **lucide** binding so the component keeps
the bare name:

| Repo | File | Collision |
|---|---|---|
| OSS | `FileUpload.jsx`, `FileWidget.jsx` | `Upload` icon vs antd's `Upload` **component** — would have broken both upload widgets |
| OSS | `Workflows.jsx` | local `User` component rendered itself — **infinite recursion** |
| Cloud | `ManageDocs`, `PdfViewer`, `Home`, `Administration` | `Upload` icon vs component |
| Cloud | `ResultEditor` | `Table` icon vs component |
| Cloud | `LandingPage` | `Tag` icon vs component |
| Cloud | `ReviewHeader` | `List` used as **both** an icon and antd's List component |

These are build breaks, not cosmetic issues — the build and the overlay gate
are what surfaced them.
