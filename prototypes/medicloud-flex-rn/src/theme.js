export const C = {
  ink: '#0A1A2F',
  inkSoft: '#31485E',
  teal: '#0E8F8B',
  mint: '#D8F2EF',
  amber: '#F5A623',
  rose: '#C2483F',
  slate: '#64748B',
  line: '#E7EDF1',
  lineSoft: '#EEF2F5',
  border: '#E2E8F0',
  bg: '#EEF3F5',
  white: '#FFFFFF',
  onInk: '#9FB3C2',
};

// Provenance tags from the pre-build briefing's labelling convention (Part I3).
// Every figure shown in the app carries one, so a number's status is never ambiguous.
export const TAG = {
  CASE: {key: 'CASE', label: 'CASE', color: C.teal, bg: C.mint,
    note: 'Stated in Ivey case W20043 — defensible by pointing at a page.'},
  ARITHMETIC: {key: 'ARITHMETIC', label: 'ARITH', color: '#8A6100', bg: '#FDF0D5',
    note: 'Calculated from case numbers. Working is shown.'},
  ANALYSIS: {key: 'ANALYSIS', label: 'ANALYSIS', color: C.inkSoft, bg: '#E3EAF0',
    note: 'An argument. Defensible but contestable.'},
  VERIFY: {key: 'VERIFY', label: 'VERIFY', color: C.rose, bg: '#FBE6E4',
    note: 'Outside the case. Must be confirmed from a primary source before use.'},
};
