# Startup Law Library — Android app (native, offline-first)

A native Kotlin / Jetpack Compose app. No WebView: the whole library ships inside the app and
opens instantly with no connection. When the phone is online the app quietly downloads the
latest signed library and, if a newer build is published, offers a one-tap update.

- **Content**: `app/src/main/assets/content.json` (built in). Live updates come from the
  `startup-law-content` branch → signed by CI with the app's release key → release
  `startup-law-content`. The app accepts a download only if the signature matches its own
  signing certificate and the revision is newer.
- **Progress**: stored only on the phone (`progress.json`, included in Android backup).
- **Screens**: Library (volumes, lessons), Cases, Founder playbook (stories, term-sheet traps),
  Practice (quiz, flashcards), Progress map, Loopholes, Updates, Search, Tutor, Sync & app.
- **Tutor**: finds the matching library notes offline; online, "Ask Claude" opens Claude with
  the question and those notes filled in.
- **Updates**: release `startup-law-latest` → `StartupLawLibrary.apk`. The app checks the
  release, downloads, verifies it is this app signed with the same key, then installs over itself.

## Release process
Every push: unit tests → build → virtual Pixel 6 (Android 14) test (`tests/emulator-test.sh`:
instrumented walk through every screen with screenshots, install over the current published
build, release-build tabs, online sync, offline mode, reconnect, rotation, resume, scrolling,
2000-event monkey test). Only if all pass is the APK published.
