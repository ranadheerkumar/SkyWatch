import type { ChangeEvent } from "react";

export type SortOption = {
  value: string;
  label: string;
};

type SortControlProps = {
  value: string;
  options: SortOption[];
  onChange: (value: string) => void;
  label?: string;
};

export default function SortControl({ value, options, onChange, label = "Sort by" }: SortControlProps) {
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value);

  return (
    <label className="table-sort-control">
      <span>{label}</span>
      <select value={value} onChange={handleChange}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}
