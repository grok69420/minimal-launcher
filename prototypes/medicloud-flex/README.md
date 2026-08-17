# Medicloud Flex — prototype

A UI prototype for **Option B** in the Medicloud Singapore case (Ivey W20043): bypass the
insurers and act as a flexible-benefit provider straight to SME employees, using the existing
clinic panel.

This is **unrelated to the `minimal-launcher` Android app** in the rest of this repository. It
lives on its own branch, in its own folder, and is not wired into the React Native build.

## What it shows

Two roles, toggled from the header:

- **Employee** — a S$500 annual benefit rendered as a blister-pack strip (one capsule per S$25),
  a panel-clinic list with capped member pricing, booking with slot selection and a cost
  breakdown, and a scannable benefit card. Booking deducts from the balance live.
- **HR** — cost versus a group outpatient policy, enrolment stats, spend by category, and the
  revenue model (S$8/employee/month + 10% clinic commission vs. the ~40% a TPA takes).

## Files

| File | What it is |
| --- | --- |
| `index.html` | Self-contained runnable prototype. No build, no dependencies, no network. |
| `App.jsx` | The original React source, kept for porting into a real React app. |

### Running it

Open `index.html` in any browser — that is the whole setup.

### About `App.jsx`

The original source targets **web React** and needs `react-dom`, Tailwind CSS, and
`lucide-react`. None of those are in this repository, so it will not build here as-is. It is
kept verbatim as the reference implementation; `index.html` is a dependency-free port of it
(plain CSS instead of Tailwind, inline SVG instead of `lucide-react`, a small vanilla-JS state
loop instead of hooks).

All figures, clinic names, prices, and the QR codes are invented for the prototype.
