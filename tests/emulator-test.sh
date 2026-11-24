#!/usr/bin/env bash
# Runs on a virtual Android phone in GitHub Actions before any build is published.
set -uo pipefail
APK=StartupLawLibrary.apk
PKG=com.abhi.startuplaw
OUT=test-shots
mkdir -p "$OUT"
: > "$OUT/report.txt"
pip install -q pillow >/dev/null 2>&1

log()     { echo "$*" | tee -a "$OUT/report.txt"; }
fail()    { log "FAILED: $1"; adb logcat -d > "$OUT/logcat.txt"; cleanup; exit 1; }
quiet()   { adb shell cmd statusbar collapse >/dev/null 2>&1
            adb shell am broadcast -a android.intent.action.CLOSE_SYSTEM_DIALOGS >/dev/null 2>&1; }
shot()    { quiet; sleep 1; adb exec-out screencap -p > "$OUT/$1.png"; log "  screenshot $1"; }
alive()   { adb shell pidof "$PKG" >/dev/null || fail "app not running after $1"; }
nocrash() { if adb logcat -d -b crash | grep -q "$PKG"; then fail "app crashed during $1"; fi; }
applog()  { adb logcat -d -s StartupLaw:I > "$OUT/applog.txt"; }
front()   { adb shell dumpsys activity activities | grep -m1 -E "topResumedActivity|mResumedActivity"; }
# Image checks: "content" = screen is not blank; "lime" = the library's lime accent is on screen.
img()     { python3 - "$OUT/$2.png" "$1" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB').resize((180, 400))
px = list(im.getdata())
if sys.argv[2] == 'content':
    sys.exit(0 if len(set(px)) > 40 else 1)
lime = sum(1 for r, g, b in px if abs(r-174) < 30 and abs(g-240) < 30 and abs(b-46) < 45)
sys.exit(0 if lime > 20 else 1)
PY
}
# Take a screenshot, retrying for up to ~30 s until it shows content.
shot_content() { for i in 1 2 3 4 5 6; do shot "$1"; img content "$1" && return 0; sleep 5; done; fail "$2 stayed blank"; }

SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; adb shell am force-stop com.android.chrome >/dev/null 2>&1; true; }
trap cleanup EXIT

# Settle the freshly booted phone: hide "app isn't responding" pop-ups from the cold start.
adb shell settings put global hide_error_dialogs 1 >/dev/null 2>&1
# Google Play services restarts itself shortly after a cold boot and takes apps that use
# its font provider with it, so let the phone settle before testing.
for i in $(seq 1 18); do
  [ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ] && break; sleep 5
done
sleep 90; quiet; adb shell input keyevent KEYCODE_HOME
adb logcat -c
log "Device: $(adb shell getprop ro.product.model) / Android $(adb shell getprop ro.build.version.release)"

log "1. Install"
adb install -r "$APK" >/dev/null || fail "install"
log "  installed $(adb shell dumpsys package $PKG | grep -m1 versionName | tr -d ' ')"

log "2. First launch loads the library"
adb shell am start -W -n "$PKG/.MainActivity" --es mode app >/dev/null
sleep 20; alive launch; nocrash launch
shot_content 01-launch "first launch"
applog
grep -q "page https://claude.ai" "$OUT/applog.txt" || fail "library page did not load"
grep -q "config ok" "$OUT/applog.txt" || fail "remote settings (config.json) not loaded"
grep -q "latest build" "$OUT/applog.txt" || fail "update check did not run"
log "  page loaded, remote settings loaded, update check ran"

log "3. Rotate to landscape and back"
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1; sleep 6; alive rotation; nocrash rotation
shot_content 02-landscape "landscape view"
adb shell settings put system user_rotation 0; sleep 4

log "4. Leave and come back"
adb shell input keyevent KEYCODE_HOME; sleep 3
adb shell am start -n "$PKG/.MainActivity" >/dev/null; sleep 6; alive resume; nocrash resume
front | grep -q "$PKG" || fail "app not in front after resume"
shot_content 03-resume "resumed app"

log "5. claude.ai sign-in link opens in the app"
adb shell am start -W -a android.intent.action.VIEW -d "https://claude.ai/login" -n "$PKG/.MainActivity" >/dev/null
sleep 10; alive "sign-in link"; nocrash "sign-in link"
shot_content 04-signin-link "sign-in page"

log "6. Chrome mode (Google sign-in path)"
adb shell am start -W -n "$PKG/.MainActivity" --es mode chrome >/dev/null
sleep 12; nocrash "chrome mode"; shot 05-chrome-tab
adb shell input keyevent KEYCODE_BACK; sleep 4; alive "chrome home"; nocrash "chrome home"
front | grep -q "$PKG" || fail "Chrome-mode home screen not shown after Back"
shot 06-chrome-home; img lime 06-chrome-home || fail "Chrome-mode home screen missing its lime button"

log "7. Switch back to in-app mode"
adb shell am start -W -n "$PKG/.MainActivity" --es mode app >/dev/null
sleep 10; alive "app mode"; nocrash "app mode"
shot_content 07-app-mode "in-app mode"

log "8. Offline screen"
adb shell svc wifi disable; adb shell svc data disable
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" --es mode app >/dev/null
sleep 8; alive offline; nocrash offline
shot 08-offline; img lime 08-offline || fail "offline screen not shown"
applog; grep -q "offline screen" "$OUT/applog.txt" || fail "offline screen not logged"
adb shell svc wifi enable; adb shell svc data enable; sleep 5

log "9. Every library screen in the phone's Chrome (test data)"
python3 - <<'PY'
src = open('tests/web/library.html').read(); mock = open('tests/web/mock.js').read()
open('tests/web/index.html', 'w').write(src.replace('<script>\n{', '<script>' + mock + '</script><script>\n{', 1))
PY
python3 -m http.server 8000 --directory tests/web >/dev/null 2>&1 &
SERVER_PID=$!
sleep 2
adb root >/dev/null 2>&1; sleep 3; adb wait-for-device
adb shell 'echo "_ --disable-fre --no-default-browser-check --no-first-run" > /data/local/tmp/chrome-command-line'
adb shell am set-debug-app --persistent com.android.chrome >/dev/null 2>&1
adb shell am force-stop com.android.chrome
for v in home map founders cases gaps quiz cards updates tutor; do
  adb shell am start -a android.intent.action.VIEW -d "http://10.0.2.2:8000/index.html?v=$v#$v" com.android.chrome >/dev/null
  sleep 7
  front | grep -q "com.android.chrome" || fail "Chrome not showing the '$v' screen"
  shot "web-$v"
  img lime "web-$v" || fail "library screen '$v' did not render (no lime accent visible)"
done
cleanup; SERVER_PID=""
adb unroot >/dev/null 2>&1; sleep 3; adb wait-for-device

log "10. Stress test: 400 random taps and swipes in the app"
adb shell monkey -p "$PKG" --throttle 250 --pct-syskeys 0 -v 400 > "$OUT/monkey.txt" 2>&1 || fail "random-input test found a crash"
nocrash "random input"; quiet

adb logcat -d > "$OUT/logcat.txt"
log "ALL TESTS PASSED"
