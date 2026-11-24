#!/usr/bin/env bash
# Runs on a virtual Android phone in GitHub Actions before any build is published.
set -uo pipefail
APK=StartupLawLibrary.apk
PKG=com.abhi.startuplaw
OUT=test-shots
mkdir -p "$OUT"
: > "$OUT/report.txt"

log()   { echo "$*" | tee -a "$OUT/report.txt"; }
fail()  { log "FAILED: $1"; adb logcat -d > "$OUT/logcat.txt"; exit 1; }
shot()  { adb exec-out screencap -p > "$OUT/$1.png"; log "  screenshot $1"; }
alive() { adb shell pidof "$PKG" >/dev/null || fail "app not running after $1"; }
nocrash() { if adb logcat -d -b crash | grep -q "$PKG"; then fail "app crashed during $1"; fi; }
applog() { adb logcat -d -s StartupLaw:I > "$OUT/applog.txt"; }

adb logcat -c
log "Device: $(adb shell getprop ro.product.model) / Android $(adb shell getprop ro.build.version.release)"

log "1. Install"
adb install -r "$APK" >/dev/null || fail "install"
log "  installed $(adb shell dumpsys package $PKG | grep -m1 versionName | tr -d ' ')"

log "2. First launch loads the library"
adb shell am start -W -n "$PKG/.MainActivity" --es mode app >/dev/null
sleep 25; alive launch; nocrash launch; shot 01-launch
applog
grep -q "page https://claude.ai" "$OUT/applog.txt" || fail "library page did not load"
grep -q "config ok" "$OUT/applog.txt" || fail "remote settings (config.json) not loaded"
grep -q "latest build" "$OUT/applog.txt" || fail "update check did not run"
log "  page loaded, remote settings loaded, update check ran"

log "3. Rotate to landscape and back"
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1; sleep 6; alive rotation; nocrash rotation; shot 02-landscape
adb shell settings put system user_rotation 0; sleep 4

log "4. Leave and come back"
adb shell input keyevent KEYCODE_HOME; sleep 3
adb shell am start -n "$PKG/.MainActivity" >/dev/null; sleep 6; alive resume; nocrash resume; shot 03-resume

log "5. claude.ai sign-in link opens in the app"
adb shell am start -W -a android.intent.action.VIEW -d "https://claude.ai/login" -n "$PKG/.MainActivity" >/dev/null
sleep 12; alive "sign-in link"; nocrash "sign-in link"; shot 04-signin-link

log "6. Chrome mode (Google sign-in path)"
adb shell am start -W -n "$PKG/.MainActivity" --es mode chrome >/dev/null
sleep 14; nocrash "chrome mode"; shot 05-chrome-tab
adb shell input keyevent KEYCODE_BACK; sleep 4; shot 06-chrome-home; alive "chrome home"; nocrash "chrome home"

log "7. Switch back to in-app mode"
adb shell am start -W -n "$PKG/.MainActivity" --es mode app >/dev/null
sleep 12; alive "app mode"; nocrash "app mode"; shot 07-app-mode

log "8. Stress test: 400 random taps and swipes"
adb shell monkey -p "$PKG" --throttle 250 --pct-syskeys 0 -v 400 > "$OUT/monkey.txt" 2>&1 || fail "random-input test found a crash"
nocrash "random input"

log "9. Offline screen"
adb shell svc wifi disable; adb shell svc data disable
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" --es mode app >/dev/null
sleep 10; alive offline; nocrash offline; shot 08-offline
applog; grep -q "offline screen" "$OUT/applog.txt" || fail "offline screen not shown"
adb shell svc wifi enable; adb shell svc data enable

adb logcat -d > "$OUT/logcat.txt"
log "ALL TESTS PASSED"
