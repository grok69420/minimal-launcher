# Medicloud Flex — React Native app

The Option B prototype for the Medicloud Singapore case (Ivey W20043), built as a real
React Native app: bypass insurance and act as a flexible-benefit provider on Medicloud's own
clinic panel.

Sources: the Option A and Option B decks, and the pre-build adversarial briefing.

## Separate from the launcher

Unrelated to the `minimal-launcher` Android app in the repository root. It has its own
`package.json`, its own `node_modules`, and its own `android/` project. The root
`metro.config.js` blocks `prototypes/` from the launcher's module graph, and `.easignore.txt`
keeps it out of the launcher's EAS uploads.

## What the briefing changed

The earlier web prototype (`../medicloud-flex/`) modelled the product in a way the briefing
attacks directly. This app fixes three things and is the current version:

**1. It names the legal structure (Part E1).** A benefits business that takes a fixed payment
and then bears the uncertain cost of care is bearing risk, which is what insurance regulation
governs. The app implements the **discount panel + administration** structure — the employee
pays the actual negotiated cost of care, and Medicloud never promises to cover future cost —
and shows the rejected prepaid/capitated alternative beside it. The old prototype's "nothing
to pay, nothing to claim" framing read as the prepaid structure, i.e. as unlicensed insurance.

**2. It stops calling the account an employer allowance (Part B3).** The case describes
flexible benefits as funded by payroll deduction from *before-tax* income. The wallet now
splits the account into the employee's payroll deduction and the employer contribution,
because the buyer and the payer are not the same party.

**3. The HR dashboard reports aggregates only (Parts E2/F2).** Employer-visible utilisation
tied to a named employee is a consent problem regardless of statute, so the product does not
offer it — and the dashboard says why.

It also concedes, rather than defends, the attacks the briefing flags as fair: the margin pool
is claimed only against the TPA's S$40 administration slice and not the full S$60; the S$265
CAC appears nowhere as a forward-looking metric; and BookDoc is acknowledged as already
selling a corporate clinic panel with an employer dashboard.

## Provenance tags

Every figure carries its status, following the briefing's labelling convention:

| Tag | Meaning |
| --- | --- |
| `CASE` | Stated in the Ivey case — defensible by pointing at a page. |
| `ARITH` | Calculated from case figures; the working is shown on screen. |
| `ANALYSIS` | An argument. Defensible but contestable. |
| `VERIFY` | Outside the case. Must be confirmed from a primary source before use. |

All figures live in `src/data/caseData.js`, each with its tag and source sentence.

## The three roles

- **Employee** — account funded by pre-tax payroll deduction, panel clinics filtered by
  district, booking with a cost breakdown showing the commission split and who bears cost
  risk, and a benefit card.
- **HR** — avoided spend against the case's entry-policy midpoint (with the caveat that it is
  not like-for-like cover), the metrics from slide 8, clinic density per district, aggregate
  utilisation, and the kill criterion.
- **Case** — the defence screen: structure, unit economics, and the attack surface with each
  attack marked *answer*, *concede*, or *unresolved*.

## Running it

```bash
cd prototypes/medicloud-flex-rn
npm install
npm test          # 9 behavioural tests covering all three roles
npm start         # Metro bundler
npm run android   # requires an Android SDK and a device/emulator
```

## Building an APK

**Not possible in the Claude Code container.** The Android SDK is downloaded from
`dl.google.com`, which the session's egress policy blocks (403 on CONNECT), so `sdkmanager`
cannot install the platform and build-tools Gradle needs. Maven Central, `maven.google.com`,
Gradle and npm are all reachable — it is specifically the SDK download host.

Two ways to get an APK:

1. **EAS Build (cloud).** `eas.json` here defines a `preview` profile that emits an APK.
   Compilation happens on Expo's servers, so no local SDK is needed:
   ```bash
   npx eas-cli build --platform android --profile preview
   ```
   Requires an Expo account and `EXPO_TOKEN` in CI.

2. **Locally, on a machine with the Android SDK.** `npm run android`, or
   `cd android && ./gradlew assembleRelease`.

The JS side is verified independently of either: `npx react-native bundle --platform android
--dev false` compiles the whole app the way a release build does, and it succeeds.

All clinic names, prices, employee and employer names are invented for the prototype. The
case figures they sit against are real and tagged.
