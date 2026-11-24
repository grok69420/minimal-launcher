# Startup Law Library — Android app

A thin Android shell around the Startup Law Library artifact
(https://claude.ai/artifact/DKsSn81Jr9f7GRAm4Rt1rq).

The app shows the hosted library full screen, so **any UI/UX or content change published
to the artifact appears in the app automatically** (on next open, or after 30 minutes away).
The app only needs rebuilding if the native shell itself changes.

- Download: Releases → `startup-law-latest` → `StartupLawLibrary.apk`
- Build: GitHub Actions (`.github/workflows/startup-law-android.yml`) on every push to this branch
- Sign in to claude.ai once inside the app; the session is kept.
- Links to sources open in your normal browser; claude.ai sign-in links can open in the app.
