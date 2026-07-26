# antd icons → lucide-react (P1-01)

Covers **all 43** `@ant-design/icons` imports across **91 OSS files**
(`src/plugins/` is cloud-owned and mapped separately in Phase C).

Every target name was verified to exist in the installed `lucide-react` build
before this table was written.

## Sizing / colour convention

antd icons inherit `font-size` and `color`; lucide icons take `size`/`className`.
The conversion uses Tailwind classes so the rendered size stays the same:

| antd context | lucide replacement |
|---|---|
| default inline icon (14px) | `className="size-3.5"` |
| icon inside a `Button` | `className="size-4"` |
| explicit `style={{ fontSize: N }}` | `className="size-[Npx]"` |
| colour via `style={{ color }}` | keep the same inline style, or `text-*` |

`lucide-react` icons are `currentColor`-driven like antd's, so inherited colour
needs no change.

## Exact mappings (safe, 1:1 in meaning)

| antd | lucide | uses |
|---|---|---|
| `DeleteOutlined` | `Trash2` | 42 |
| `EditOutlined` | `Pencil` | 28 |
| `PlusOutlined` | `Plus` | 27 |
| `CopyOutlined` | `Copy` | 23 |
| `SearchOutlined` | `Search` | 21 |
| `ArrowLeftOutlined` | `ArrowLeft` | 21 |
| `ReloadOutlined` | `RotateCw` | 20 |
| `InfoCircleOutlined` | `Info` | 19 |
| `UserOutlined` | `User` | 17 |
| `CheckCircleOutlined` | `CircleCheck` | 17 |
| `FileTextOutlined` | `FileText` | 15 |
| `PlayCircleOutlined` | `CirclePlay` | 12 |
| `SettingOutlined` | `Settings` | 8 |
| `FilterOutlined` | `Filter` | 8 |
| `ClockCircleOutlined` | `Clock` | 8 |
| `TableOutlined` | `Table` | 7 |
| `CloudDownloadOutlined` | `CloudDownload` | 6 |
| `UploadOutlined` | `Upload` | 4 |
| `UnorderedListOutlined` | `List` | 4 |
| `CloseOutlined` | `X` | 4 |
| `ArrowDownOutlined` | `ArrowDown` | 4 |
| `MinusOutlined` | `Minus` | 2 |
| `InboxOutlined` | `Inbox` | 2 |
| `DownloadOutlined` | `Download` | 2 |
| `CloudUploadOutlined` | `CloudUpload` | 2 |
| `CheckOutlined` | `Check` | 2 |
| `ArrowUpOutlined` | `ArrowUp` | 2 |
| `ExclamationCircleOutlined` | `CircleAlert` | 2 |
| `FullscreenOutlined` | `Maximize` | 2 |
| `FullscreenExitOutlined` | `Minimize` | 2 |
| `ExpandOutlined` | `Expand` | 2 |
| `DownOutlined` | `ChevronDown` | 6 |
| `UpOutlined` | `ChevronUp` | 4 |

## ⚠ Non-1:1 pairs — REVIEW THESE

lucide has no equivalent of antd's *filled* variants, and a few names carry
different connotations. Each of these is a deliberate judgement call:

| antd | lucide | uses | Why it's not exact |
|---|---|---|---|
| `CheckCircleFilled` | `CircleCheck` | 10 | **lucide has no filled variant.** Renders as an outline where antd drew a solid glyph. Visually lighter. If the solid look matters (status indicators), add `fill-current` or use `className="fill-success text-white"`. |
| `PlayCircleFilled` | `CirclePlay` | 8 | Same filled→outline caveat. |
| `InfoCircleFilled` | `Info` | 8 | Same, plus antd's is a circled glyph plain `Info` also draws a circle, so this one is close. |
| `QuestionCircleOutlined` | `CircleHelp` | 19 | lucide renamed `HelpCircle` → `CircleHelp`. Same glyph, different name. |
| `MoreOutlined` | **`EllipsisVertical`** | 10 | antd's `MoreOutlined` renders **vertical** (⋮), so plain `Ellipsis` (horizontal …) would be wrong. `EllipsisVertical` is the correct target and is what the migration applies. |
| `CaretDownOutlined` | `ChevronDown` | 2 | antd's caret is a **solid triangle**; lucide's chevron is a **thin stroke**. Closest available; `ChevronDown` matches the shadcn/Radix idiom used elsewhere. |
| `ScheduleOutlined` | `CalendarClock` | 4 | antd's is a clipboard-with-check; lucide has no direct match. `CalendarClock` fits the scheduling context these call-sites are in. Alternative: `ClipboardCheck`. |
| `FileExclamationOutlined` | `FileWarning` | 3 | Equivalent meaning, different glyph detail. |
| `ArrowsAltOutlined` | `Move` | 2 | antd's is a 4-way expand arrow; `Move` is the closest. If the intent was "expand", use `Maximize2`. |
| `BarChartOutlined` | `ChartColumn` | 2 | lucide renamed `BarChart` → `ChartColumn`. Same glyph. |

### Recommendation for the filled variants

`CheckCircleFilled` (10) and `PlayCircleFilled` (8) are the only mappings that
change the visual *weight* of an icon rather than its shape. Both are used as
status/action affordances where the solid fill carries meaning. Suggested
treatment when converting:

```jsx
// antd:   <CheckCircleFilled style={{ color: "#52c41a" }} />
// lucide: filled look via fill + stroke on the same token
<CircleCheck className="size-3.5 fill-success text-white" />
```

## Not affected

- No deep imports (`@ant-design/icons/...`) exist — 0 occurrences.
- No default-import form (`import Icon from "@ant-design/icons"`) — 0 occurrences.
- All 91 files use the named-import form, so the conversion is mechanical.
