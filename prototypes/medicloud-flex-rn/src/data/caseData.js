/* Every figure in this prototype traces to the Ivey case (W20043), to arithmetic on case
   figures, to argument, or to something still unverified. Tags follow the pre-build
   briefing's convention so the provenance of a number is never ambiguous on screen. */

export const FIGURES = {
  tpaTake: {value: 40, of: 100, tag: 'CASE',
    text: 'On a $100 visit the doctor pays $40 to the TPA and delivers $60 of care. The TPA also caps what the clinic may charge.'},
  gpVisit: {lo: 30, hi: 100, tag: 'CASE', text: 'Cost of a GP visit without insurance cover.'},
  dental: {lo: 100, hi: 150, tag: 'CASE', text: 'Cost of dental services without insurance cover.'},
  outpatientAnnual: {lo: 500, hi: 700, tag: 'CASE',
    text: 'Annual outpatient and primary care spend per working person, not covered by government insurance.'},
  smeFlexi: {lo: 300, hi: 500, tag: 'CASE', text: 'Flexible benefits per SME employee per year.'},
  mncFlexi: {lo: 1000, hi: 2000, tag: 'CASE', text: 'Flexible benefits per MNC employee per year.'},
  entryPolicy: {lo: 1000, hi: 1500, tag: 'CASE',
    text: 'Entry-level policy per employee. Insurers also require hospitalisation cover to qualify for basic outpatient cover.'},
  insurerMinGroup: {value: 500, tag: 'CASE', text: 'Minimum group size insurers require, from Teo’s own industry experience.'},
  smeShare: {value: 99, tag: 'CASE', text: 'SMEs are 99% of enterprises and employ 65% of the working population.'},
  engagement: {value: 73, regional: 80, tag: 'CASE',
    text: 'Singapore employee engagement, lowest in Asia-Pacific, against a regional average of 80% (Mercer).'},
  clinics: {value: 50, tag: 'CASE', text: 'Clinics on panel at the September 2017 decision point.'},
  cac: {value: 265, tag: 'CASE', text: 'Average cost to attract one download, inclusive of HR, technology and marketing.'},
  devSpend: {value: 300000, tag: 'CASE', text: 'Paid to a third-party developer for the MVP over two years.'},
  salaries: {value: 15000, tag: 'CASE', text: 'Monthly salary burn: founding team plus two temporary admin staff.'},
  angel: {value: 1000000, tag: 'CASE', text: 'Angel funding raised one year after founding, pre-revenue.'},
  twoYearSpend: {value: 660000, tag: 'ARITHMETIC',
    text: 'SG$300,000 development + (SG$15,000 × 24 months) salaries = SG$660,000 identified spend.'},
  costPerClinic: {value: 13200, tag: 'ARITHMETIC',
    text: 'SG$660,000 across 50 clinics = about SG$13,200 per clinic, ignoring all other spend.'},
  yearOneAcq: {value: 132500, tag: 'ARITHMETIC', text: '500 downloads × SG$265 = SG$132,500 in year one.'},
};

/* The employee's account. Per Part B3 of the briefing, a flexible benefit is funded by
   payroll deduction from BEFORE-TAX income — it is largely the employee's own money routed
   for tax efficiency, not an employer handout. The wording here is deliberate. */
export const ACCOUNT = {
  holder: 'Wei Ling Tan',
  employer: 'Tai Seng Logistics Pte Ltd',
  headcount: 42,
  planYear: 2026,
  annual: 500,          // top of the case's SG$300–500 SME flexi-benefit band [CASE]
  employerTopUp: 200,   // illustrative split — employer contribution vs payroll deduction
  cardLast4: '4417',
};

export const DISTRICTS = [
  {id: 'tsg', name: 'Tai Seng', live: 21, target: 50},
  {id: 'bmh', name: 'Bukit Merah', live: 17, target: 50},
  {id: 'twn', name: 'Tuas West', live: 12, target: 50},
];

export const CLINICS = [
  {id: 1, name: 'Bukit Merah Family Clinic', type: 'GP', district: 'bmh',
   icon: 'gp', km: 0.4, wait: 10, rate: 38, list: 70},
  {id: 2, name: 'Tanjong Pagar Dental', type: 'Dental', district: 'bmh',
   icon: 'dental', km: 1.1, wait: 25, rate: 110, list: 150},
  {id: 3, name: 'Paya Lebar Family Practice', type: 'GP', district: 'tsg',
   icon: 'gp', km: 1.6, wait: 15, rate: 42, list: 75},
  {id: 4, name: 'Tai Seng Medical', type: 'GP', district: 'tsg',
   icon: 'gp', km: 2.0, wait: 5, rate: 35, list: 65},
  {id: 5, name: 'Tai Seng Dental Studio', type: 'Dental', district: 'tsg',
   icon: 'dental', km: 2.3, wait: 20, rate: 105, list: 140},
  {id: 6, name: 'Tuas West Occupational Health', type: 'GP', district: 'twn',
   icon: 'gp', km: 4.8, wait: 8, rate: 40, list: 70},
];

export const SEED_VISITS = [
  {id: 'c1', place: 'Bukit Merah Family Clinic', type: 'GP visit', amt: 38, date: '12 Aug'},
  {id: 'c2', place: 'Tai Seng Medical', type: 'GP visit', amt: 35, date: '28 Jul'},
  {id: 'c3', place: 'Tanjong Pagar Dental', type: 'Scaling', amt: 110, date: '09 Jul'},
];

/* Medicloud's commission, charged to the clinic, deliberately set below the TPA's 40%.
   Part G1 #3 of the briefing: the defensible margin pool is the TPA's $40 administration
   slice, NOT the full $60 that does not reach the doctor. */
export const COMMISSION_PCT = 10;

/* Part E1 — the structure question that decides whether Option B is insurance.
   The briefing is explicit: naming the structure removes the strongest legal attack. */
export const STRUCTURES = [
  {
    id: 'discount',
    name: 'Discount panel + administration',
    chosen: true,
    mechanics: 'Medicloud negotiates rates with clinics. The employee pays the actual negotiated cost of care from their flexi-benefit account. Medicloud earns an access and administration fee.',
    risk: 'Medicloud bears no cost risk. Care consumed above the account balance is simply paid by the employee.',
    verdict: 'Almost certainly not insurance — this is the structure that keeps the venture outside the Insurance Act.',
    tag: 'ANALYSIS',
  },
  {
    id: 'prepaid',
    name: 'Prepaid / capitated membership',
    chosen: false,
    mechanics: 'Employer or employee pays a fixed monthly per-head fee. Medicloud pays for whatever care is consumed.',
    risk: 'Transfers utilisation risk to Medicloud — it bears the uncertain cost of future events in exchange for a fixed payment.',
    verdict: 'Functionally insurance business, and would likely require authorisation. Rejected for this prototype.',
    tag: 'VERIFY',
  },
];

/* Part B2 — Teo's claim that no player occupies this segment is contradicted by the case. */
export const COMPETITORS = [
  {name: 'BookDoc', note: 'Corporate clients, own panel clinics, and an employer analytics dashboard. Closest to Option B and already in market.', tag: 'CASE'},
  {name: 'CXA Group', note: 'Newcomer explicitly targeting niche markets including SMEs.', tag: 'CASE'},
  {name: 'DocDoc', note: 'First mover, 110,000+ doctors, reviews and recommendations.', tag: 'CASE'},
  {name: 'Rewardz', note: 'Engagement via gamification. Teo dismisses it, but the case offers no data that SME employees prefer cost savings over engagement.', tag: 'CASE'},
];

/* Slide 8 of the Option B deck: the guardrail that makes the recommendation falsifiable. */
export const KILL_CRITERION =
  'If clinics will not contract below TPA commission levels after 60 days of negotiation, revert to Option A and monetise Teo’s insurer network instead.';

export const METRICS = [
  {label: 'Employees under subscription', value: '42'},
  {label: 'Clinics live per district', value: '21 / 17 / 12'},
  {label: 'Monthly recurring revenue', value: 'S$336'},
  {label: 'Utilisation rate', value: '62%'},
  {label: 'Gross margin vs TPA benchmark', value: '+30 pts'},
];
