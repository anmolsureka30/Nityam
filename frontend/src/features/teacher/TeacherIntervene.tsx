import { useState } from "react";
import { TeacherShell } from "../../components/Shell";
import { Button, Label } from "../../components/ui";
import { atRisk } from "../../lib/data";
import type { AtRiskStudent } from "../../lib/types";
import s from "./teacher.module.css";

type Filter = "all" | "critical" | "inactive";

const SEV_CLASS: Record<AtRiskStudent["severity"], string> = {
  critical: s.sevCritical,
  watch: s.sevWatch,
  inactive: s.sevInactive,
};

/* Ranked by how much a two-minute conversation would move them, not by lowest
 * mastery. A teacher has about six minutes before the bell; the list has to be
 * spendable, not exhaustive. */
export default function TeacherIntervene() {
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set(atRisk.map((r) => r.id)));

  const counts = {
    all: atRisk.length,
    critical: atRisk.filter((r) => r.severity === "critical").length,
    inactive: atRisk.filter((r) => r.severity === "inactive").length,
  };
  const rows = atRisk.filter((r) => filter === "all" || r.severity === filter);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <TeacherShell>
      <div className={s.head}>
        <div>
          <h1 className={s.title}>Needs attention before tomorrow</h1>
          <div className={s.meta}>Ranked by how much a two-minute conversation would move them</div>
        </div>
        <div className={s.filters} role="group" aria-label="Filter students">
          {([["all", "All"], ["critical", "Critical"], ["inactive", "Inactive"]] as const).map(
            ([id, label]) => (
              <button
                key={id}
                className={`${s.filter} ${filter === id ? s.filterOn : ""}`}
                aria-pressed={filter === id}
                onClick={() => setFilter(id)}
              >
                {label} {counts[id]}
              </button>
            ),
          )}
        </div>
      </div>

      <table className={s.table}>
        <thead>
          <tr>
            <th style={{ width: 34 }}><span className="sr-only">Selected</span></th>
            <th>Student</th>
            <th style={{ width: 78 }}>Mastery</th>
            <th>Named misconception</th>
            <th>Evidence</th>
            <th style={{ width: 110 }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(r.id)}
                  onChange={() => toggle(r.id)}
                  aria-label={`Include ${r.name}`}
                />
              </td>
              <td className={s.name}>
                <span className={`${s.sev} ${SEV_CLASS[r.severity]}`} aria-hidden="true" />
                {r.name}
              </td>
              <td className={s.num}>{r.mastery === 0 ? "—" : `${r.mastery}%`}</td>
              <td>{r.misconception}</td>
              <td className={s.evidence}>{r.evidence}</td>
              <td>
                <Button size="sm">Assign drill</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={s.footBar}>
        <Label>
          {selected.size} selected · est. {Math.max(2, selected.size * 2)} min of class time
        </Label>
        <Button variant="primary" size="sm" disabled={selected.size === 0}>
          Assign all as tonight's homework
        </Button>
      </div>
    </TeacherShell>
  );
}
