/**
 * F32 — shared filter bar for the search + documents pages.
 *
 * Pure controlled component. Owner pages keep ``FilterState`` in
 * page-level useState; the bar reads ``value`` and emits ``onChange``
 * on every chip / picker / date / numeric edit.
 *
 * Skill suggestions come from the F32 ``GET /api/search/skills``
 * endpoint (canonical KNOWN_SKILLS). Free-text input also commits
 * chips so a skill not in the canonical vocab still filters
 * correctly — the suggestion list is a UX hint, not a contract.
 *
 * Date inputs use native ``<input type="date">`` for v1; the bar
 * normalises ``date_to`` to end-of-day (23:59:59) on commit so the
 * operator's "through May 9" reads as inclusive of that whole day.
 */

import { useId, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { XIcon } from "lucide-react";

import { listKnownSkillsOptions } from "@/api";
import type { DocumentType } from "@/api/generated";
import {
  EMPTY_FILTERS,
  type FilterState,
  isAnyFilterActive,
} from "@/components/documents/document-filter-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const DOC_TYPES: { label: string; value: DocumentType | "" }[] = [
  { label: "Any type", value: "" },
  { label: "Resume", value: "resume" },
  { label: "Report", value: "report" },
  { label: "Contract", value: "contract" },
  { label: "Letter", value: "letter" },
  { label: "Other", value: "other" },
];

interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
}

export function DocumentFilterBar({ value, onChange }: Props) {
  const typeId = useId();
  const skillsId = useId();
  const expId = useId();
  const fromId = useId();
  const toId = useId();

  const [skillInput, setSkillInput] = useState("");

  const { data: skillOptions = [] } = useQuery({
    ...listKnownSkillsOptions(),
  });

  const remainingSuggestions = useMemo(
    () => skillOptions.filter((s) => !value.skills.includes(s)),
    [skillOptions, value.skills]
  );

  const filteredSuggestions = useMemo(() => {
    const q = skillInput.trim().toLowerCase();
    if (!q) return remainingSuggestions.slice(0, 50);
    return remainingSuggestions.filter((s) => s.includes(q)).slice(0, 50);
  }, [remainingSuggestions, skillInput]);

  // ---- chip handlers ----

  const addSkill = (raw: string) => {
    const cleaned = raw.trim().toLowerCase();
    if (!cleaned || value.skills.includes(cleaned)) return;
    onChange({ ...value, skills: [...value.skills, cleaned] });
    setSkillInput("");
  };
  const removeSkill = (s: string) =>
    onChange({ ...value, skills: value.skills.filter((x) => x !== s) });

  return (
    <div className="flex flex-col gap-3 rounded-lg border p-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
        {/* Type */}
        <Field>
          <FieldLabel htmlFor={typeId}>Document type</FieldLabel>
          <Select
            value={value.document_type ?? ""}
            onValueChange={(v) =>
              onChange({
                ...value,
                document_type: (v || null) as DocumentType | null,
              })
            }
          >
            <SelectTrigger id={typeId}>
              <SelectValue placeholder="Any type" />
            </SelectTrigger>
            <SelectContent>
              {DOC_TYPES.map((t) => (
                <SelectItem key={t.value || "any"} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {/* Skills */}
        <Field className="lg:col-span-2">
          <FieldLabel htmlFor={skillsId}>Skills (all of)</FieldLabel>
          <Combobox<string>
            items={filteredSuggestions}
            itemToStringValue={(s) => s ?? ""}
            itemToStringLabel={(s) => s ?? ""}
            onValueChange={(picked) => {
              if (typeof picked === "string" && picked) addSkill(picked);
            }}
          >
            <ComboboxInput
              id={skillsId}
              placeholder="python, react, …  (Enter to add)"
              value={skillInput}
              onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addSkill(skillInput);
                }
              }}
            />
            <ComboboxContent>
              <ComboboxEmpty>
                Press Enter to add "{skillInput.trim()}"
              </ComboboxEmpty>
              <ComboboxList>
                {(item: string) => (
                  <ComboboxItem key={item} value={item}>
                    {item}
                  </ComboboxItem>
                )}
              </ComboboxList>
            </ComboboxContent>
          </Combobox>
        </Field>

        {/* Min experience years */}
        <Field>
          <FieldLabel htmlFor={expId}>Min. years</FieldLabel>
          <Input
            id={expId}
            type="number"
            min={0}
            max={30}
            placeholder="any"
            value={value.min_experience_years ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              onChange({
                ...value,
                min_experience_years: v === "" ? null : Number(v),
              });
            }}
          />
        </Field>

        {/* Date range */}
        <Field>
          <FieldLabel htmlFor={fromId}>Uploaded after</FieldLabel>
          <Input
            id={fromId}
            type="date"
            value={value.date_from ?? ""}
            onChange={(e) =>
              onChange({ ...value, date_from: e.target.value || null })
            }
          />
        </Field>

        <Field>
          <FieldLabel htmlFor={toId}>Uploaded before</FieldLabel>
          <Input
            id={toId}
            type="date"
            value={value.date_to ?? ""}
            onChange={(e) =>
              onChange({ ...value, date_to: e.target.value || null })
            }
          />
        </Field>
      </div>

      {/* Active filter chips + clear-all */}
      {isAnyFilterActive(value) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {value.document_type && (
            <Chip
              label={`type: ${value.document_type}`}
              onClear={() => onChange({ ...value, document_type: null })}
            />
          )}
          {value.skills.map((s) => (
            <Chip key={s} label={s} onClear={() => removeSkill(s)} />
          ))}
          {value.min_experience_years !== null && (
            <Chip
              label={`${value.min_experience_years}+ yrs`}
              onClear={() =>
                onChange({ ...value, min_experience_years: null })
              }
            />
          )}
          {value.date_from && (
            <Chip
              label={`after ${value.date_from}`}
              onClear={() => onChange({ ...value, date_from: null })}
            />
          )}
          {value.date_to && (
            <Chip
              label={`before ${value.date_to}`}
              onClear={() => onChange({ ...value, date_to: null })}
            />
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="ml-1"
          >
            Clear all
          </Button>
        </div>
      )}
    </div>
  );
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <Badge variant="secondary" className="gap-1 text-xs">
      <span>{label}</span>
      <button
        type="button"
        onClick={onClear}
        aria-label={`Remove filter ${label}`}
        className="hover:text-destructive focus-visible:ring-ring rounded focus-visible:ring-2 focus-visible:outline-none"
      >
        <XIcon className="size-3" />
      </button>
    </Badge>
  );
}
