"use client";

import type { Section } from "../types";
import HomePage from "./page";

export default function SectionRoute({ section }: { section: Section }) {
  return <HomePage initialSection={section} />;
}
