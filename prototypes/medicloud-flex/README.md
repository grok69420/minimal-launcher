# Medicloud Flex — prototype (superseded)

> **Superseded by [`../medicloud-flex-rn/`](../medicloud-flex-rn/).** That React Native app is
> the current version. It was rebuilt against the case decks and the pre-build adversarial
> briefing, which attack this prototype's model on three points: it presents the account as an
> employer allowance when the case describes payroll deduction from before-tax income; its
> "nothing to pay, nothing to claim" framing reads as a prepaid, risk-bearing structure —
> functionally insurance — rather than a discount panel; and its HR dashboard implies
> employer-visible utilisation. This copy is kept as the original design study only. Do not
> present its figures.

A UI prototype for **Option B** in the Medicloud Singapore case (Ivey W20043): bypass the
insurers and act as a flexible-benefit provider straight to SME employees, using the existing
clinic panel.

## Separate from the launcher

This is **unrelated to the `minimal-launcher` Android app** in the repository root, and is kept
fully isolated from it:

- its own `package.json` and `node_modules` — it shares no dependencies with the app;
- excluded from Metro via `blockList` in the root `metro.config.js`, so the React Native
  bundler never sees it;
- listed in `.easignore.txt`, so it is not uploaded to EAS builds;
- lives on the `claude/medicloud-flex-prototype-qkcp6s` branch, not merged to the default branch.

Nothing here is imported by the Android app, and nothing here imports from it.

## What it shows

Two roles, toggled from the header:

- **Employee** — a S$500 annual benefit rendered as a blister-pack strip (one capsule per S$25),
  a panel-clinic list with capped member pricing, booking with slot selection and a cost
  breakdown, and a scannable benefit card. Booking deducts from the balance live.
- **HR** — cost versus a group outpatient policy, enrolment stats, spend by category, and the
  revenue model (S$8/employee/month + 10% clinic commission vs. the ~40% a TPA takes).

## Running it

There are two ways in, and they are independent.

### 1. The React app (React + Vite + Tailwind + lucide-react)

```bash
cd prototypes/medicloud-flex
npm install
npm run dev        # dev server with hot reload
```

`npm run build` emits `dist/`, and `npm run preview` serves that production build. The built
app must be **served**, not opened from disk — its entry is an ES module, and browsers refuse
to load those over `file://`.

### 2. `standalone.html` — no build, no install

Open the file in a browser. That is the whole setup: no dependencies, no build step, no
network. It is a hand-port of the same UI using plain CSS instead of Tailwind, inline SVG
instead of `lucide-react`, and a small vanilla-JS state loop instead of hooks.

Useful for sending the prototype to someone who should not have to run `npm install`. Because
it is a separate implementation, a change to `src/App.jsx` does **not** appear here — the two
have to be updated together.

## Layout

| Path | What it is |
| --- | --- |
| `src/App.jsx` | The prototype. Original source, unmodified. |
| `src/main.jsx` | React entry point. |
| `src/index.css` | Tailwind directives. |
| `index.html` | Vite entry. |
| `standalone.html` | Dependency-free port of the same UI. |

All figures, clinic names, prices, and the QR codes are invented for the prototype.
