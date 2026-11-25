#!/usr/bin/env bash
# Virtual-phone test run in GitHub Actions before any build reaches a real phone.
set -uo pipefail
PKG=com.abhi.startuplaw
DBG=com.abhi.startuplaw.debug
OUT=test-shots
mkdir -p "$OUT"
: > "$OUT/report.txt"
pip install -q pillow >/dev/null 2>&1

log()     { echo "$*" | tee -a "$OUT/report.txt"; }
fail()    { log "FAILED: $1"; adb logcat -d > "$OUT/logcat.txt"; exit 1; }
quiet()   { adb shell cmd statusbar collapse >/dev/null 2>&1; }
shot()    { quiet; sleep 1; adb exec-out screencap -p > "$OUT/$1.png"; log "  screenshot $1"; }
alive()   { adb shell pidof "$PKG" >/dev/null || fail "app not running after $1"; }
nocrash() { if adb logcat -d -b crash | grep -qE "$PKG"; then adb logcat -d -b crash > "$OUT/crash.txt"; fail "app crashed during $1"; fi; }
ui()      { python3 tests/ui.py "$@"; }
tap()     { for i in 1 2 3 4 5; do ui tap "$1" && { sleep 2; return 0; }; sleep 2; done; ui dump > "$OUT/ui-missing.txt"; fail "could not find '$1' on screen"; }
has()     { for i in 1 2 3 4 5 6; do ui has "$1" && return 0; sleep 2; done; return 1; }
launch()  { adb shell am start -W -n "$PKG/.MainActivity" | tee -a "$OUT/report.txt" | grep -E "TotalTime" || true; }
# "content" = the screenshot is not blank; "ice" = the app's cyan accent is visible.
img()     { python3 - "$OUT/$2.png" "$1" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB')
w, h = im.size
im = im.crop((0, int(h * 0.06), w, int(h * 0.93))).resize((180, 400))
px = list(im.getdata())
if sys.argv[2] == 'content':
    sys.exit(0 if len(set(px)) > 40 else 1)
ice = sum(1 for r, g, b in px if abs(r-143) < 40 and abs(g-232) < 35 and abs(b-255) < 30)
sys.exit(0 if ice > 8 else 1)
PY
}
check_shot() { shot "$1"; img content "$1" || fail "$1 is blank"; img ice "$1" || fail "$1 does not show the app"; }

# Let the freshly booted phone settle.
adb shell settings put global hide_error_dialogs 1 >/dev/null 2>&1
for i in $(seq 1 24); do [ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ] && break; sleep 5; done
sleep 45; quiet; adb shell input keyevent KEYCODE_HOME
adb logcat -c
log "Device: $(adb shell getprop ro.product.model) / Android $(adb shell getprop ro.build.version.release)"

log "1. Walk every screen (instrumented UI test, debug build)"
adb install -r app-debug.apk >/dev/null || fail "install debug build"
adb install -r app-debug-androidTest.apk >/dev/null || fail "install UI test"
adb shell am instrument -w -r -e class com.abhi.startuplaw.AppFlowTest "$DBG.test/androidx.test.runner.AndroidJUnitRunner" > "$OUT/ui-test.txt" 2>&1
mkdir -p "$OUT/ui"
adb exec-out run-as "$DBG" tar -cf - files/shots 2>/dev/null | tar -xf - -C "$OUT/ui" 2>/dev/null
log "  $(ls "$OUT/ui/files/shots" 2>/dev/null | wc -l) step screenshots"
if ! grep -q "OK (1 test)" "$OUT/ui-test.txt"; then
  grep -E "Error|Exception|at com.abhi" "$OUT/ui-test.txt" | head -30 | tee -a "$OUT/report.txt"
  adb logcat -d > "$OUT/logcat.txt"
  fail "UI test failed (see ui-test.txt)"
fi
log "  UI test passed"
adb uninstall "$DBG.test" >/dev/null 2>&1; adb uninstall "$DBG" >/dev/null 2>&1
adb logcat -c

log "2. Install over the build phones have now"
if [ -f previous.apk ]; then
  adb install previous.apk >/dev/null || fail "install previous build"
  log "  previous: $(adb shell dumpsys package $PKG | grep -m1 versionName | tr -d ' ')"
  adb shell am start -n "$PKG/.MainActivity" >/dev/null 2>&1; sleep 8
  adb shell am force-stop "$PKG"
  adb install -r StartupLawLibrary.apk > "$OUT/upgrade.txt" 2>&1 || { cat "$OUT/upgrade.txt" | tee -a "$OUT/report.txt"; fail "new build will not install over the current one"; }
  log "  upgraded in place"
else
  adb install -r StartupLawLibrary.apk >/dev/null || fail "install"
fi
log "  now: $(adb shell dumpsys package $PKG | grep -m1 versionName | tr -d ' ')"

log "3. Release build opens"
launch; sleep 6
alive "launch"; nocrash "launch"
check_shot release-home
adb logcat -d -s StartupLaw:* > "$OUT/applog.txt"
grep -q "loaded" "$OUT/applog.txt" || fail "library did not load"
log "  $(grep -m1 loaded "$OUT/applog.txt" | sed 's/.*StartupLaw: //')"

log "4. Online sync"
for i in $(seq 1 15); do adb logcat -d -s StartupLaw:* | grep -qE "sync: |sync failed|sync rejected" && break; sleep 2; done
adb logcat -d -s StartupLaw:* > "$OUT/applog.txt"
grep -E "sync" "$OUT/applog.txt" | sed 's/.*StartupLaw: /  /' | tee -a "$OUT/report.txt"
grep -q "signature does not match" "$OUT/applog.txt" && fail "published library is not signed with the app key"
grep -q "did not validate" "$OUT/applog.txt" && fail "published library did not validate"

log "5. Every tab on the release build"
for t in Cases Playbook Practice Progress Library; do tap "$t"; alive "$t"; nocrash "$t"; check_shot "release-$t"; done
tap "Loopholes"; check_shot release-loopholes; adb shell input keyevent KEYCODE_BACK; sleep 2
tap "Ask the tutor"; check_shot release-tutor; adb shell input keyevent KEYCODE_BACK; sleep 2

log "6. Offline"
adb shell svc wifi disable; adb shell svc data disable; sleep 5
adb shell am force-stop "$PKG"; launch; sleep 5
alive "offline launch"; nocrash "offline launch"
check_shot offline-home
has "Offline. Open sync settings" || fail "offline state not shown"
tap "Cases"; check_shot offline-cases
tap "Practice"; check_shot offline-practice
tap "Library"
log "  works offline"
adb logcat -c
adb shell svc wifi enable; adb shell svc data enable
for i in $(seq 1 20); do ui has "Online. Open sync settings" && break; sleep 3; done
has "Online. Open sync settings" || fail "did not notice the connection coming back"
shot back-online
log "  noticed the connection returning"

log "7. Rotate, background, resume"
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1; sleep 3; alive "rotate"; check_shot landscape
adb shell settings put system user_rotation 0; sleep 3
adb shell input keyevent KEYCODE_HOME; sleep 3
launch; sleep 3; alive "resume"; nocrash "resume"; check_shot resumed

log "8. Scroll smoothness (informational on a software-rendered emulator)"
adb shell dumpsys gfxinfo "$PKG" reset >/dev/null
for i in 1 2 3 4 5 6; do adb shell input swipe 540 1800 540 500 250; sleep 0.5; done
for i in 1 2 3; do adb shell input swipe 540 600 540 1900 250; sleep 0.5; done
adb shell dumpsys gfxinfo "$PKG" | grep -E "Total frames rendered|Janky frames|50th percentile|90th percentile" | sed 's/^/  /' | tee -a "$OUT/report.txt"

log "9. Monkey test (2000 random taps and swipes)"
adb shell monkey -p "$PKG" --pct-syskeys 0 --pct-appswitch 2 --throttle 50 -s 4242 -v 2000 > "$OUT/monkey.txt" 2>&1
grep -qE "CRASH|ANR in" "$OUT/monkey.txt" && { grep -A20 -E "CRASH|ANR" "$OUT/monkey.txt" | head -40 | tee -a "$OUT/report.txt"; fail "monkey found a crash"; }
nocrash "monkey"
grep -q "Monkey finished" "$OUT/monkey.txt" || fail "monkey did not finish"
launch; sleep 2; alive "after monkey"; check_shot after-monkey

adb logcat -d > "$OUT/logcat.txt"
log "ALL PHONE TESTS PASSED"
