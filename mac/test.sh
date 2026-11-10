#!/bin/sh
# Builds the QA app (QA=1 ARCH=arm64) and runs the desktop suites that work on the Mac, then prints a table.
#  sh mac/test.sh               every Mac suite
#  sh mac/test.sh polish ...    just these (any suite in tests/desktop)
# Run it in a Terminal on the Mac or over SSH while you're logged in: the suites open real Still windows.
set -u
cd "$(dirname "$0")/.."
QA=1 ARCH=arm64 sh mac/build.sh || exit 1
exe=mac/build/qa/Still.app/Contents/MacOS/Still
python=${PYTHON:-python3} # 3.10 or newer (welcome.py); Homebrew's python3 works
logs=artifacts/mac-test
mkdir -p "$logs"

# QA builds keep WebKit data, caches, saved windows and defaults under their own bundle id. Each suite starts without
# them, as each Windows suite starts on its own profile, and the run leaves nothing behind.
clean() {
 for dir in WebKit Caches HTTPStorages "Saved Application State"; do rm -rf "$HOME/Library/$dir"/com.carbongotfound.still.qa*; done
 rm -rf "${TMPDIR:-/tmp}/com.carbongotfound.still.qa" # WebKit's own temp folders there are sandboxed: macOS clears them
 defaults delete com.carbongotfound.still.qa 2>/dev/null
}

printf '%-12s %-6s %5s %5s  %s\n' suite result pass fail log
failed=0
for suite in ${*:-mascots polish tab_tools tabs memory companions popovers permissions stepstate actions seen agentic welcome agents providers claudelogin}; do
 clean
 "$python" "tests/desktop/$suite.py" "$exe" > "$logs/$suite.log" 2>&1
 code=$?
 pass=$(grep -c '^PASS ' "$logs/$suite.log")
 fail=$(grep -c '^FAIL ' "$logs/$suite.log")
 if [ "$code" = 0 ] && [ "$fail" = 0 ] && [ "$pass" -gt 0 ]; then result=pass; else result=FAIL; failed=1; fi
 printf '%-12s %-6s %5s %5s  %s\n' "$suite" "$result" "$pass" "$fail" "$logs/$suite.log"
done

if [ $# = 0 ]; then
 skip() { printf '%-12s %-6s %s\n' "$1" skip "$2"; }
 skip live "talks to real AI apps: run it by name when you mean to"
 # Windows only.
 skip takeover "Win32 window hit tests"
 skip features "extensions (CRX) and DevTools need WebView2"
 skip performance "WebView2 process memory; on the Mac, run tests/desktop/baseline.py"
 skip startup "Win32 window enumeration and the launcher pipe"
fi

clean
exit $failed
