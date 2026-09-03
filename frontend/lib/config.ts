/** Search panel filter and sort configuration for each entity type. */

import { ENUMS } from "@/lib/enums"


/* ─── Filter field types ───────────────────────────────────────────────────── */
// A filter field is rendered as text / number / select / date. Some kinds
// support comparison operators (=, <, >, …); see `OPERATORS` below.

// `only` marks a field one backend cannot apply: the mirror holds no anime or
// review data, and the API has no notion of lie-flagged tags. The other backend
// refuses such a filter rather than answering emptily, so the form must not
// offer it — see `availableFilters`.
export interface BaseField { value: string; label: string; only?: "local" | "remote" }
export interface TextField extends BaseField { allowEmpty?: boolean; placeholder?: string }
export interface NumberField extends BaseField { integer?: boolean; comparable?: boolean; placeholder?: string }
export interface SelectField extends BaseField { default?: string; comparable?: boolean; iconType?: "LANGUAGE" | "PLATFORM"; options: { value: string; label: string }[] }
export interface DateField extends BaseField { availableFormats: string[]; comparable?: boolean; placeholder?: string }
export type EntityType = "tag" | "trait" | "staff" | "producer"
export interface EntityItem { id: string; label: string }
export interface EntityField extends BaseField { entityType: EntityType; spoilable?: boolean }

// A set of entity buckets presented as one combined picker: the same entity
// (tag / trait) added in different "modes" — include, directed, or exclude —
// each of which maps to its own backend filter param (`tag` / `dtag` /
// `tag_exclude`). The buckets still live in `entity`/`entityOptions` (so state
// and param-building are unchanged); this only drives the merged UI.
export type EntityMode = "include" | "directed" | "exclude"
export interface EntityGroupField {
  label: string
  entityType: EntityType
  spoilable?: boolean
  modes: { mode: EntityMode; value: string }[]
}

// Controlled state for the search panel form, grouped by field kind.
// `*Comparable` variants pair an operator with the user-entered value.
export interface FilterState {
  text: Record<string, string>
  number: Record<string, string>
  numberComparable: Record<string, { operator: string; number: string }>
  select: Record<string, string>
  selectComparable: Record<string, { operator: string; value: string }>
  date: Record<string, string>
  dateComparable: Record<string, { operator: string; date: string }>
  entity: Record<string, EntityItem[]>
  // Per-entity-filter toggles for tag/dtag/trait/dtrait: `spoil` raises the
  // match to the Major spoiler level, `lie` (local only) drops lie-flagged tags.
  entityOptions: Record<string, { spoil: boolean; lie: boolean }>
}

/* ─── Validation ───────────────────────────────────────────────────────────── */

export const OPERATORS = ["=", "<", ">", "<=", ">=", "!="]

// Pre-compiled regex for each supported date format used in date filters.
const DATE_FORMAT_REGEX: Record<string, RegExp> = {
  "yyyy-mm-dd": /^(19|20)\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/,
  "yyyy-mm": /^(19|20)\d{2}-(0[1-9]|1[0-2])$/,
  "yyyy": /^(19|20)\d{2}$/,
  "mm-dd": /^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/,
  "mm": /^(0[1-9]|1[0-2])$/,
}

// Cheap "is this what the user is currently typing" check — used to gate
// keystrokes so the input only accepts digits (and optionally a decimal point).
export const isValidNumberInput = (input: string, integer?: boolean): boolean =>
  input === "" ? true : integer ? /^\d+$/.test(input) : /^\d*\.?\d+$/.test(input)

// Same idea for dates: allow digits and dashes while typing.
export const isValidDateInput = (input: string): boolean =>
  input === "" ? true : /^[\d-]*$/.test(input)

// Strict check used at submit time. When `comparable`, an optional operator
// prefix (=, <, >, <=, >=, !=) is allowed before the number.
export const isValidNumber = (input: string, comparable?: boolean, integer?: boolean): boolean => {
  if (!input || input.trim() === "" || input.trim() === "= ") return false
  const r = comparable
    ? (integer ? /^(=|<|>|<=|>=|!=)?\d+$/ : /^(=|<|>|<=|>=|!=)?\d*\.?\d+$/)
    : (integer ? /^\d+$/ : /^\d*\.?\d+$/)
  return r.test(input.replace(/\s/g, ""))
}

// Strict check used at submit time. When `comparable`, peels off the leading
// operator and validates the remainder; otherwise matches `format` verbatim
// and runs calendar bounds (e.g. February days).
export const isValidDate = (input: string, format: string, comparable = false): boolean => {
  if (!input || input.trim() === "" || input.trim() === "= ") return false
  if (comparable) {
    const m = input.replace(/\s/g, "").match(/^(=|<|>|<=|>=|!=)(.*)$/)
    if (!m) return isValidDate(input, format, false)
    return isValidDate(m[2].trim(), format, false)
  }
  const fmt = format.toLowerCase()
  const regex = DATE_FORMAT_REGEX[fmt]
  if (!regex || !regex.test(input)) return false
  const nextYear = new Date().getFullYear() + 1
  if (fmt === "yyyy-mm-dd") {
    const [y, mo, d] = input.split("-").map(Number)
    if (y < 1900 || y > nextYear || mo < 1 || mo > 12) return false
    return d >= 1 && d <= new Date(y, mo, 0).getDate()
  }
  if (fmt === "yyyy-mm") { const [y, mo] = input.split("-").map(Number); return y >= 1900 && y <= nextYear && mo >= 1 && mo <= 12 }
  if (fmt === "yyyy") { const y = Number(input); return y >= 1900 && y <= nextYear }
  if (fmt === "mm-dd") {
    const [mo, d] = input.split("-").map(Number)
    if (mo < 1 || mo > 12) return false
    return d >= 1 && d <= new Date(2000, mo, 0).getDate()
  }
  if (fmt === "mm") { const mo = Number(input); return mo >= 1 && mo <= 12 }
  return false
}

// A select is "valid" (i.e. meant to constrain the query) when it isn't the
// "Any" sentinel and isn't empty.
export const isValidSelect = (value: string, comparable = false): boolean => {
  if (comparable) {
    const m = value.match(/^(=|<|>|<=|>=|!=)(.*)$/)
    if (!m) return isValidSelect(value, false)
    return m[2].trim().toLowerCase() !== "any" && m[2].trim() !== ""
  }
  return value.toLowerCase() !== "any" && value !== ""
}

/* ─── Filter definitions (per entity type) ─────────────────────────────────── */
// Adding a new field here automatically wires it into the search panel form,
// initial state, and query parameter builder.

export const searchFilters: Record<string, { text?: TextField[]; number?: NumberField[]; select?: SelectField[]; date?: DateField[]; entity?: EntityField[]; entityGroups?: EntityGroupField[] }> = {
  v: {
    entityGroups: [
      {
        label: "Tag", entityType: "tag", spoilable: true,
        modes: [
          { mode: "include",  value: "tag" },
          { mode: "directed", value: "dtag" },
          { mode: "exclude",  value: "tag_exclude" },
        ],
      },
    ],
    entity: [
      { value: "tag",         label: "Tag",          entityType: "tag", spoilable: true },
      { value: "dtag",        label: "Directed Tag", entityType: "tag", spoilable: true },
      { value: "tag_exclude", label: "Exclude Tag",  entityType: "tag", spoilable: true },
      { value: "staff",       label: "Staff",        entityType: "staff" },
      { value: "developer",   label: "Developer",    entityType: "producer" },
    ],
    text: [
      { value: "release",   label: "Release" },
      { value: "character", label: "Character" },
    ],
    number: [
      { value: "rating", label: "Rating", integer: true, comparable: true, placeholder: "Bayesian rating 10–100" },
      { value: "votecount", label: "Vote Count", integer: true, comparable: true, placeholder: "Number of votes" },
    ],
    select: [
      { value: "lang", label: "Language", default: "any", iconType: "LANGUAGE", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.LANGUAGE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "olang", label: "Original Language", default: "ja", iconType: "LANGUAGE", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.LANGUAGE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "platform", label: "Platform", default: "any", iconType: "PLATFORM", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.PLATFORM).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "length", label: "Length", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.LENGTH).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "devstatus", label: "Dev Status", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.DEVSTATUS).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "has_description", label: "Has Description", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "has_anime", label: "Has Anime", default: "any", only: "remote", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "has_screenshot", label: "Has Screenshot", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "has_review", label: "Has Review", default: "any", only: "remote", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
    ],
    date: [{ value: "released", label: "Release Date", availableFormats: ["YYYY-MM-DD", "YYYY-MM", "YYYY"], comparable: true, placeholder: "YYYY-MM-DD / YYYY-MM / YYYY" }],
  },
  r: {
    entity: [
      { value: "producer", label: "Producer", entityType: "producer" },
    ],
    text: [
      { value: "engine",  label: "Engine" },
      { value: "extlink", label: "External Link" },
      { value: "vn",     label: "Visual Novel" },
    ],
    number: [{ value: "minage", label: "Minimum Age", integer: true, comparable: true, placeholder: "Integer" }],
    select: [
      { value: "lang", label: "Language", default: "any", iconType: "LANGUAGE", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.LANGUAGE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "platform", label: "Platform", default: "any", iconType: "PLATFORM", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.PLATFORM).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "medium", label: "Medium", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.MEDIUM).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "voiced", label: "Voiced", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.VOICED).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "rtype", label: "Release Type", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.RTYPE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "patch", label: "Patch", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "freeware", label: "Freeware", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "uncensored", label: "Uncensored", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "official", label: "Official", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
      { value: "has_ero", label: "Has Ero", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
    ],
    date: [{ value: "released", label: "Release Date", availableFormats: ["YYYY-MM-DD", "YYYY-MM", "YYYY"], comparable: true, placeholder: "YYYY-MM-DD / YYYY-MM / YYYY" }],
  },
  c: {
    entityGroups: [
      {
        label: "Trait", entityType: "trait", spoilable: true,
        modes: [
          { mode: "include",  value: "trait" },
          { mode: "directed", value: "dtrait" },
          { mode: "exclude",  value: "trait_exclude" },
        ],
      },
    ],
    entity: [
      { value: "trait",         label: "Trait",          entityType: "trait", spoilable: true },
      { value: "dtrait",        label: "Directed Trait",  entityType: "trait", spoilable: true },
      { value: "trait_exclude", label: "Exclude Trait",   entityType: "trait", spoilable: true },
      { value: "seiyuu",        label: "Seiyuu",          entityType: "staff" },
    ],
    text: [
      { value: "vn", label: "Visual Novel" },
    ],
    number: [
      { value: "height", label: "Height (cm)", integer: true, comparable: true, placeholder: "Integer" },
      { value: "weight", label: "Weight (kg)", integer: true, comparable: true, placeholder: "Integer" },
      { value: "bust", label: "Bust (cm)", integer: true, comparable: true, placeholder: "Integer" },
      { value: "waist", label: "Waist (cm)", integer: true, comparable: true, placeholder: "Integer" },
      { value: "hips", label: "Hips (cm)", integer: true, comparable: true, placeholder: "Integer" },
      { value: "age", label: "Age", integer: true, comparable: true, placeholder: "Integer" },
    ],
    select: [
      { value: "role", label: "Role", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.CHARACTER_ROLE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "blood_type", label: "Blood Type", default: "any", options: [{ value: "any", label: "Any" }, { value: "a", label: "A" }, { value: "b", label: "B" }, { value: "ab", label: "AB" }, { value: "o", label: "O" }] },
      { value: "sex", label: "Sex", default: "any", options: [{ value: "any", label: "Any" }, { value: "m", label: "Male" }, { value: "f", label: "Female" }, { value: "b", label: "Both" }, { value: "n", label: "Sexless" }] },
      { value: "sex_spoil", label: "Sex (Spoil)", default: "any", options: [{ value: "any", label: "Any" }, { value: "m", label: "Male" }, { value: "f", label: "Female" }, { value: "b", label: "Both" }, { value: "n", label: "Sexless" }] },
      { value: "cup", label: "Cup Size", default: "any", comparable: true, options: [{ value: "any", label: "Any" }, { value: "AAA", label: "AAA" }, { value: "AA", label: "AA" }, ...Array.from({ length: 26 }, (_, i) => ({ value: String.fromCharCode(65 + i), label: String.fromCharCode(65 + i) }))] },
    ],
    date: [{ value: "birthday", label: "Birthday", availableFormats: ["MM-DD", "MM"], placeholder: "MM-DD or MM" }],
  },
  p: {
    text: [{ value: "extlink", label: "External Link" }],
    select: [
      { value: "lang", label: "Language", default: "any", iconType: "LANGUAGE", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.LANGUAGE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "type", label: "Type", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.TYPE).map(([k, v]) => ({ value: k, label: v }))] },
    ],
  },
  s: {
    text: [{ value: "extlink", label: "External Link" }],
    select: [
      { value: "lang", label: "Language", default: "any", iconType: "LANGUAGE", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.LANGUAGE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "gender", label: "Gender", default: "any", options: [{ value: "any", label: "Any" }, { value: "m", label: "Male" }, { value: "f", label: "Female" }] },
      { value: "role", label: "Role", default: "any", only: "remote", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.STAFF_ROLE).map(([k, v]) => ({ value: k, label: v }))] },
      { value: "ismain", label: "Is Main", default: "any", options: [{ value: "any", label: "Any" }, { value: "1", label: "Yes" }, { value: "0", label: "No" }] },
    ],
  },
  g: {
    select: [
      { value: "category", label: "Category", default: "any", options: [{ value: "any", label: "Any" }, ...Object.entries(ENUMS.CATEGORY).map(([k, v]) => ({ value: k, label: v }))] },
    ],
  },
  i: {},
}

/* ─── Filter state helpers ─────────────────────────────────────────────────── */

// The fields of `type` that `source` can actually apply. `both` keeps every
// field: it routes each query to whichever backend can serve it.
export function availableFilters(type: string, source?: string) {
  const f = searchFilters[type] || {}
  const usable = <T extends BaseField>(fields?: T[]): T[] =>
    (fields || []).filter(x => !x.only || !source || source === "both" || x.only === source)
  return {
    entityGroups: f.entityGroups || [],
    entity: usable(f.entity),
    text: usable(f.text),
    number: usable(f.number),
    select: usable(f.select),
    date: usable(f.date),
  }
}

// Produces a blank `FilterState` for the given entity type, seeded with the
// per-field defaults declared in `searchFilters`.
export function buildInitialState(type: string): FilterState {
  const f = searchFilters[type] || {}
  return {
    text: Object.fromEntries((f.text || []).map(x => [x.value, ""])),
    number: Object.fromEntries((f.number || []).filter(x => !x.comparable).map(x => [x.value, ""])),
    numberComparable: Object.fromEntries((f.number || []).filter(x => x.comparable).map(x => [x.value, { operator: "=", number: "" }])),
    select: Object.fromEntries((f.select || []).filter(x => !x.comparable).map(x => [x.value, x.default || "any"])),
    selectComparable: Object.fromEntries((f.select || []).filter(x => x.comparable).map(x => [x.value, { operator: "=", value: "any" }])),
    date: Object.fromEntries((f.date || []).filter(x => !x.comparable).map(x => [x.value, ""])),
    dateComparable: Object.fromEntries((f.date || []).filter(x => x.comparable).map(x => [x.value, { operator: "=", date: "" }])),
    entity: Object.fromEntries((f.entity || []).map(x => [x.value, []])),
    entityOptions: Object.fromEntries(
      (f.entity || []).filter(x => x.spoilable).map(x => [x.value, { spoil: false, lie: false }])
    ),
  }
}

// Reduces a `FilterState` to a flat `{ field: value }` map suitable for the
// API query string. Invalid / empty entries are dropped silently.
export function buildFilterParams(type: string, state: FilterState, source?: string): Record<string, string> {
  const f = availableFilters(type, source)
  const result: Record<string, string> = {}

  // The state outlives a change of source, so a value entered for a field this
  // source cannot apply is still in it. It must not travel with the query.
  const offered = new Set(
    [...f.text, ...f.number, ...f.select, ...f.date, ...f.entity].map(x => x.value))

  for (const [k, v] of Object.entries(state.text)) {
    if (offered.has(k) && v.trim()) result[k] = v.trim()
  }
  for (const [k, v] of Object.entries(state.number)) {
    const field = f.number.find(x => x.value === k)
    if (field && isValidNumber(v, false, field.integer)) result[k] = v.trim()
  }
  for (const [k, v] of Object.entries(state.numberComparable)) {
    const field = f.number.find(x => x.value === k)
    const combined = `${v.operator} ${v.number}`.trim()
    if (field && isValidNumber(combined, true, field.integer)) result[k] = combined
  }
  for (const [k, v] of Object.entries(state.select)) {
    if (offered.has(k) && isValidSelect(v, false)) result[k] = v
  }
  for (const [k, v] of Object.entries(state.selectComparable)) {
    const combined = `${v.operator} ${v.value}`.trim()
    if (offered.has(k) && isValidSelect(combined, true)) result[k] = combined
  }
  for (const [k, v] of Object.entries(state.date)) {
    const field = f.date.find(x => x.value === k)
    if (field && field.availableFormats.some(fmt => isValidDate(v, fmt, false))) result[k] = v.trim()
  }
  for (const [k, v] of Object.entries(state.dateComparable)) {
    const combined = `${v.operator} ${v.date}`.trim()
    const field = f.date.find(x => x.value === k)
    if (field && field.availableFormats.some(fmt => isValidDate(combined, fmt, true))) result[k] = combined
  }
  for (const [k, v] of Object.entries(state.entity || {})) {
    if (v.length === 0 || !offered.has(k)) continue
    const ids = v.map(item => item.id).join(",")
    const opt = state.entityOptions?.[k]
    if (opt?.spoil) {
      // `exclude lies` is a local-only refinement — the Kana API can't filter
      // lie-flagged tags — so only emit it when the local backend is queried.
      result[opt.lie && source === "local" ? `${k}_spoil_exclude_lies` : `${k}_spoil`] = ids
    } else {
      result[k] = ids
    }
  }

  return result
}

/* ─── Sort options (per entity type) ───────────────────────────────────────── */
// Each type lists sort columns under three buckets:
//   - `both`   — available against either backend
//   - `remote` — VNDB-only (e.g. search rank)
//   - `local`  — fields that only the local DB indexes (e.g. `created_at`)

export const SORT_OPTIONS: Record<string, {
  both?: { value: string; label: string }[]
  remote?: { value: string; label: string }[]
  local?: { value: string; label: string }[]
}> = {
  v: {
    both: [
      { value: "id", label: "Id" },
      { value: "title", label: "Title" },
      { value: "released", label: "Release Date" },
      { value: "rating", label: "Bayesian Rating" },
      { value: "votecount", label: "Vote Count" },
    ],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [
      { value: "average", label: "Raw Vote Average" },
      { value: "length_minutes", label: "Length (Minutes)" },
      { value: "created_at", label: "Created At" },
    ],
  },
  r: {
    both: [
      { value: "id", label: "Id" },
      { value: "title", label: "Title" },
      { value: "released", label: "Release Date" },
    ],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [{ value: "minage", label: "Minimum Age" }, { value: "created_at", label: "Created At" }],
  },
  c: {
    both: [
      { value: "id", label: "Id" },
      { value: "name", label: "Name" },
    ],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [
      { value: "height", label: "Height" }, { value: "weight", label: "Weight" },
      { value: "age", label: "Age" }, { value: "created_at", label: "Created At" },
    ],
  },
  p: {
    both: [{ value: "id", label: "Id" }, { value: "name", label: "Name" }],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [{ value: "created_at", label: "Created At" }],
  },
  s: {
    both: [{ value: "id", label: "Id" }, { value: "name", label: "Name" }],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [{ value: "created_at", label: "Created At" }],
  },
  g: {
    both: [
      { value: "id", label: "Id" },
      { value: "name", label: "Name" },
      { value: "vn_count", label: "VN Count" },
    ],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [{ value: "created_at", label: "Created At" }],
  },
  i: {
    both: [
      { value: "id", label: "Id" },
      { value: "name", label: "Name" },
      { value: "char_count", label: "Character Count" },
    ],
    remote: [{ value: "searchrank", label: "Search Rank" }],
    local: [{ value: "group_name", label: "Group Name" }, { value: "created_at", label: "Created At" }],
  },
}

// Returns the sort columns available for `type` under the given backend
// (`both` is always included; `remote` and `local` are mutually exclusive).
export function getSortOptions(type: string, from: string) {
  const t = SORT_OPTIONS[type]
  if (!t) return []
  if (from === "remote") return [...(t.both || []), ...(t.remote || [])]
  if (from === "local") return [...(t.both || []), ...(t.local || [])]
  return t.both || []
}

// Default sort key for `type`+`from`. Falls back to `"id"` when the type has
// no entries declared (shouldn't happen for known types).
export function getDefaultSortOption(type: string, from: string): string {
  const opts = getSortOptions(type, from)
  return opts[0]?.value ?? "id"
}
