/** Renders the per-type filter form driven by `searchFilters` in lib/config. */
"use client"

import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"
import {
  FilterState, TextField, NumberField, SelectField, DateField, EntityItem,
  OPERATORS, availableFilters,
  isValidNumberInput, isValidDateInput, isValidDate,
} from "@/lib/config"
import { EntityFilter } from "@/components/input/EntityFilter"
import { EntityModeFilter } from "@/components/input/EntityModeFilter"
import { IconSelect } from "@/components/input/IconSelect"


/* ─── Shared styles & small primitives ─────────────────────────────────────── */

const inputCls = "w-full px-3 py-2 rounded-lg bg-surface border border-white/10 text-white text-sm placeholder:text-muted focus:outline-none focus:border-white/30"
const selectCls = "appearance-none pl-3 pr-8 py-2 rounded-lg bg-surface border border-white/10 text-white text-sm focus:outline-none focus:border-white/30 cursor-pointer"

// Decorative chevron wrapper for native <select>.
function SelectWrap({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("relative", className)}>
      {children}
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
    </div>
  )
}

// Segmented operator pill row used by *Comparable filter variants.
function OperatorButtons({ value, onChange }: { value: string; onChange: (op: string) => void }) {
  return (
    <div className="flex rounded-lg border border-white/10 overflow-hidden">
      {OPERATORS.map(op => (
        <button
          key={op}
          type="button"
          onClick={() => onChange(op)}
          className={cn(
            "flex-1 py-1.5 text-xs font-mono transition-colors leading-none",
            value === op
              ? "bg-white/20 text-white"
              : "text-muted hover:text-white hover:bg-white/10"
          )}
        >
          {op}
        </button>
      ))}
    </div>
  )
}

function FieldLabel({ label }: { label: string }) {
  return <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{label}</p>
}

// Small on/off pill — used for the spoiler / lie toggles on entity filters.
function MiniToggle({ label, on, disabled, onToggle }: {
  label: string; on: boolean; disabled?: boolean; onToggle: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "px-2 py-0.5 rounded-full text-xs border transition-colors",
        disabled
          ? "border-white/5 text-muted/40 cursor-not-allowed"
          : on
            ? "border-accent/40 bg-accent/15 text-accent"
            : "border-white/10 text-muted hover:text-white hover:border-white/30",
      )}
    >
      {label}
    </button>
  )
}


/* ─── Per-field renderers (one per filter kind, with comparable variant) ───── */

function TextFilter({ filter, value, onChange }: { filter: TextField; value: string; onChange: (k: string, v: string) => void }) {
  return (
    <div>
      <FieldLabel label={filter.label} />
      <input className={inputCls} value={value} onChange={e => onChange(filter.value, e.target.value)} placeholder={filter.placeholder} />
    </div>
  )
}

function NumberFilter({ filter, value, onChange }: { filter: NumberField; value: string; onChange: (k: string, v: string) => void }) {
  return (
    <div>
      <FieldLabel label={filter.label} />
      <input className={inputCls} value={value}
        onChange={e => { if (isValidNumberInput(e.target.value, filter.integer)) onChange(filter.value, e.target.value) }}
        placeholder={filter.placeholder} />
    </div>
  )
}

function NumberFilterComparable({ filter, value, onChange }: {
  filter: NumberField
  value: { operator: string; number: string }
  onChange: (k: string, v: { operator: string; number: string }) => void
}) {
  return (
    <div>
      <FieldLabel label={filter.label} />
      <div className="flex flex-col gap-1.5">
        <OperatorButtons value={value.operator} onChange={op => onChange(filter.value, { operator: op, number: value.number })} />
        <input className={inputCls} value={value.number}
          onChange={e => { if (isValidNumberInput(e.target.value, filter.integer)) onChange(filter.value, { operator: value.operator, number: e.target.value }) }}
          placeholder={filter.placeholder} />
      </div>
    </div>
  )
}

function SelectFilter({ filter, value, onChange }: { filter: SelectField; value: string; onChange: (k: string, v: string) => void }) {
  // Language / platform: custom dropdown so each option can show its sprite icon
  // (native <option> can't render the flag/platform sprites).
  if (filter.iconType) {
    return (
      <div>
        <FieldLabel label={filter.label} />
        <IconSelect value={value} options={filter.options} iconType={filter.iconType}
          onChange={v => onChange(filter.value, v)} />
      </div>
    )
  }
  // Render as segmented buttons when there are few short-labeled options;
  // otherwise fall back to a native <select>.
  const useToggle = filter.options.length <= 3 ||
    (filter.options.length <= 5 && filter.options.every(o => o.label.length <= 3))
  if (useToggle) {
    return (
      <div>
        <FieldLabel label={filter.label} />
        <div className="flex rounded-lg border border-white/10 overflow-hidden">
          {filter.options.map(o => (
            <button
              key={o.value}
              type="button"
              onClick={() => onChange(filter.value, o.value)}
              className={cn(
                "flex-1 py-1.5 text-xs transition-colors leading-none",
                value === o.value
                  ? "bg-white/20 text-white font-medium"
                  : "text-muted hover:text-white hover:bg-white/10"
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div>
      <FieldLabel label={filter.label} />
      <SelectWrap className="w-full">
        <select className={cn(selectCls, "w-full")} value={value} onChange={e => onChange(filter.value, e.target.value)}>
          {filter.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </SelectWrap>
    </div>
  )
}

function SelectFilterComparable({ filter, value, onChange }: {
  filter: SelectField
  value: { operator: string; value: string }
  onChange: (k: string, v: { operator: string; value: string }) => void
}) {
  return (
    <div>
      <FieldLabel label={filter.label} />
      <div className="flex flex-col gap-1.5">
        <OperatorButtons value={value.operator} onChange={op => onChange(filter.value, { operator: op, value: value.value })} />
        <SelectWrap className="w-full">
          <select className={cn(selectCls, "w-full")} value={value.value}
            onChange={e => onChange(filter.value, { operator: value.operator, value: e.target.value })}>
            {filter.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </SelectWrap>
      </div>
    </div>
  )
}

function DateFilter({ filter, value, onChange }: { filter: DateField; value: string; onChange: (k: string, v: string) => void }) {
  const valid = value === "" || filter.availableFormats.some(f => isValidDate(value, f, false))
  return (
    <div>
      <FieldLabel label={filter.label} />
      <input className={cn(inputCls, !valid && "border-red-500 bg-red-500/10")}
        value={value} onChange={e => { if (isValidDateInput(e.target.value)) onChange(filter.value, e.target.value) }}
        placeholder={filter.placeholder} />
    </div>
  )
}

function DateFilterComparable({ filter, value, onChange }: {
  filter: DateField
  value: { operator: string; date: string }
  onChange: (k: string, v: { operator: string; date: string }) => void
}) {
  const valid = value.date === "" || filter.availableFormats.some(f => isValidDate(value.date, f, true))
  return (
    <div>
      <FieldLabel label={filter.label} />
      <div className="flex flex-col gap-1.5">
        <OperatorButtons value={value.operator} onChange={op => onChange(filter.value, { operator: op, date: value.date })} />
        <input className={cn(inputCls, !valid && "border-red-500 bg-red-500/10")}
          value={value.date} onChange={e => { if (isValidDateInput(e.target.value)) onChange(filter.value, { operator: value.operator, date: e.target.value }) }}
          placeholder={filter.placeholder} />
      </div>
    </div>
  )
}

/* ─── Form ─────────────────────────────────────────────────────────────────── */

interface FiltersFormProps {
  type: string
  filterState: FilterState
  source?: string
  setFilterState: (s: FilterState) => void
}

export function FiltersForm({ type, filterState, source, setFilterState }: FiltersFormProps) {
  // Only what this source can apply: a field the backend would refuse is a
  // control that can produce nothing but an error.
  const f = availableFilters(type, source)

  const setText = (k: string, v: string) => setFilterState({ ...filterState, text: { ...filterState.text, [k]: v } })
  const setNumber = (k: string, v: string) => setFilterState({ ...filterState, number: { ...filterState.number, [k]: v } })
  const setNumberComparable = (k: string, v: { operator: string; number: string }) =>
    setFilterState({ ...filterState, numberComparable: { ...filterState.numberComparable, [k]: v } })
  const setSelect = (k: string, v: string) => setFilterState({ ...filterState, select: { ...filterState.select, [k]: v } })
  const setSelectComparable = (k: string, v: { operator: string; value: string }) =>
    setFilterState({ ...filterState, selectComparable: { ...filterState.selectComparable, [k]: v } })
  const setDate = (k: string, v: string) => setFilterState({ ...filterState, date: { ...filterState.date, [k]: v } })
  const setDateComparable = (k: string, v: { operator: string; date: string }) =>
    setFilterState({ ...filterState, dateComparable: { ...filterState.dateComparable, [k]: v } })
  const setEntity = (k: string, v: EntityItem[]) =>
    setFilterState({ ...filterState, entity: { ...filterState.entity, [k]: v } })
  const entityOpt = (k: string) => filterState.entityOptions?.[k] ?? { spoil: false, lie: false }
  const setEntityOption = (k: string, patch: Partial<{ spoil: boolean; lie: boolean }>) =>
    setFilterState({
      ...filterState,
      entityOptions: { ...filterState.entityOptions, [k]: { ...entityOpt(k), ...patch } },
    })
  // A merged tag/trait group shares one spoil/lie setting across all its
  // buckets, so write the same patch to every bucket's options at once.
  const setGroupOption = (keys: string[], patch: Partial<{ spoil: boolean; lie: boolean }>) =>
    setFilterState({
      ...filterState,
      entityOptions: {
        ...filterState.entityOptions,
        ...Object.fromEntries(keys.map(k => [k, { ...entityOpt(k), ...patch }])),
      },
    })

  // Buckets rendered inside a merged group are hidden from the plain entity list.
  const groupedValues = new Set(f.entityGroups.flatMap(g => g.modes.map(m => m.value)))

  const hasAny = f.text.length || f.number.length || f.select.length || f.date.length || f.entity.length

  return (
    <div className="flex flex-col gap-4">
      {f.entityGroups.map(group => {
        const keys = group.modes.map(m => m.value)
        const opt = entityOpt(keys[0])
        return (
          <div key={group.label} className="flex flex-col gap-1.5">
            <EntityModeFilter
              label={group.label}
              entityType={group.entityType}
              modes={group.modes}
              values={Object.fromEntries(keys.map(k => [k, filterState.entity?.[k] ?? []]))}
              onChange={next => setFilterState({ ...filterState, entity: { ...filterState.entity, ...next } })}
              source={source}
            />
            {group.spoilable && (
              <div className="flex flex-wrap items-center gap-1.5">
                <MiniToggle
                  label="Include spoilers"
                  on={opt.spoil}
                  onToggle={() => setGroupOption(keys, { spoil: !opt.spoil })}
                />
                {/* `exclude lies` is local-only — the Kana API can't filter lies. */}
                {source === "local" && (
                  <MiniToggle
                    label="Exclude lies"
                    on={opt.lie}
                    disabled={!opt.spoil}
                    onToggle={() => setGroupOption(keys, { lie: !opt.lie })}
                  />
                )}
              </div>
            )}
          </div>
        )
      })}
      {f.entity.filter(field => !groupedValues.has(field.value)).map(field => (
        <div key={field.value} className="flex flex-col gap-1.5">
          <EntityFilter
            label={field.label}
            entityType={field.entityType}
            value={filterState.entity?.[field.value] ?? []}
            onChange={v => setEntity(field.value, v)}
            source={source}
          />
          {field.spoilable && (
            <div className="flex flex-wrap items-center gap-1.5">
              <MiniToggle
                label="Include spoilers"
                on={entityOpt(field.value).spoil}
                onToggle={() => setEntityOption(field.value, { spoil: !entityOpt(field.value).spoil })}
              />
              {/* `exclude lies` is local-only — the Kana API can't filter lies. */}
              {source === "local" && (
                <MiniToggle
                  label="Exclude lies"
                  on={entityOpt(field.value).lie}
                  disabled={!entityOpt(field.value).spoil}
                  onToggle={() => setEntityOption(field.value, { lie: !entityOpt(field.value).lie })}
                />
              )}
            </div>
          )}
        </div>
      ))}
      {f.text.map(field => (
        <TextFilter key={field.value} filter={field}
          value={filterState.text[field.value] ?? ""}
          onChange={setText} />
      ))}
      {f.number.map(field => field.comparable ? (
        <NumberFilterComparable key={field.value} filter={field}
          value={filterState.numberComparable[field.value] ?? { operator: "=", number: "" }}
          onChange={setNumberComparable} />
      ) : (
        <NumberFilter key={field.value} filter={field}
          value={filterState.number[field.value] ?? ""}
          onChange={setNumber} />
      ))}
      {f.select.some(field => !field.comparable) && (
        <div className="grid grid-cols-2 gap-3">
          {f.select.filter(field => !field.comparable).map(field => (
            <SelectFilter key={field.value} filter={field}
              value={filterState.select[field.value] ?? field.default ?? "any"}
              onChange={setSelect} />
          ))}
        </div>
      )}
      {f.select.filter(field => field.comparable).map(field => (
        <SelectFilterComparable key={field.value} filter={field}
          value={filterState.selectComparable[field.value] ?? { operator: "=", value: "any" }}
          onChange={setSelectComparable} />
      ))}
      {f.date.map(field => field.comparable ? (
        <DateFilterComparable key={field.value} filter={field}
          value={filterState.dateComparable[field.value] ?? { operator: "=", date: "" }}
          onChange={setDateComparable} />
      ) : (
        <DateFilter key={field.value} filter={field}
          value={filterState.date[field.value] ?? ""}
          onChange={setDate} />
      ))}
      {!hasAny && (
        <p className="text-sm text-muted text-center py-4">No filters available for this type.</p>
      )}
    </div>
  )
}
