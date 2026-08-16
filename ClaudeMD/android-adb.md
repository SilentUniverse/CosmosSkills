# Android / ADB Reference

CLAUDE.md §11 points here. All rules and lookup tables live in this file.
All traps verified live on Pixel 3 / Android 12 / Git Bash host (2026-08-16).

## Traps that break commands outright (Git Bash host)

One root cause, three symptoms — MSYS rewrites leading-`/` arguments into Windows paths:

| Symptom | Broken form | Working form |
|---|---|---|
| Device path mangled: `dumped to: /Files/Git/sdcard/…` | `adb shell uiautomator dump /sdcard/x.xml` | `adb shell "uiautomator dump /sdcard/x.xml"` — quote the whole device command |
| Pull fails: `failed to stat 'C:/Program Files/Git/sdcard/x'` — **quotes do NOT help** (pure-path arg still converted) | `adb pull /sdcard/x.xml out/` | `adb pull //sdcard/x.xml out/` — double slash on remote paths |
| `MSYS_NO_PATHCONV=1` fixes remote but local `/tmp/x` then lands at drive root (`D:\tmp\x`) | `MSYS_NO_PATHCONV=1 adb pull /sdcard/x /tmp/x` | only with Windows-form local path: `MSYS_NO_PATHCONV=1 adb pull /sdcard/x "$TEMP/x"` |

Rule of thumb: any `/`-leading argument meant for the device gets `//` (pull/push remote paths) or lives inside a quoted device command (shell). Prefer `//` — it leaves local paths untouched.

## Output is CRLF — and corrupts binaries

- Every `adb shell` line ends `\r\n` (`pidof` returns `2229\r\n` raw). Before `$(…)` or piping: `| tr -d '\r'`.
- `adb shell screencap -p > x.png` corrupts the PNG from byte 6 onward (`\r` inserted; verified 14052 vs 14050 bytes). Use either:
  - `adb exec-out screencap -p > x.png`, or
  - `adb shell "screencap -p /sdcard/x.png"` + `adb pull //sdcard/x.png`

## Stream commands — never run inline

Verified: bare `adb logcat` under `timeout 3` exits 124 (still streaming when killed).

| Command | Inline-safe form |
|---|---|
| `adb logcat` | `adb logcat -d` (+ slimming below), or background redirect |
| `adb shell top` | `adb shell top -n 1` (≈0.5 s, exits) |
| `adb shell screenrecord` | `adb shell "screenrecord --time-limit 30 /sdcard/r.mp4"` then pull |
| interactive `adb shell` | never; always `adb shell "<cmd>"` |
| `adb wait-for-device` | background it; only after reboot/reconnect |

## logcat slimming — pick ONE scope, never dump raw

| Want | Command |
|---|---|
| crash stack | `adb logcat -b crash -d` |
| last N lines | `adb logcat -d -t 500` |
| errors only | `adb logcat -d *:E` |
| one process | `adb logcat -d --pid=$(adb shell pidof com.x \| tr -d '\r')` |
| pattern match | `adb logcat -d \| rg -i "pattern"` |
| time window | absolute timestamp only: `adb logcat -d -T "07-05 16:40:00.000"` — relative `-T '2 minutes ago'` is rejected on Android 12 (`not in time format`) |

## Standard capture loop (reproduce → capture)

```bash
adb logcat -c
adb logcat -v time > .scratch/tmp/logcat.txt 2>&1   # run_in_background: true
# …trigger reproduction (am start / input tap / manual)…
# poll progress any time: tail .scratch/tmp/logcat.txt
# TaskStop the background task, then read back filtered:
rg -i "FATAL|ANR|AndroidRuntime|com.pkg" .scratch/tmp/logcat.txt
```

## uiautomator (UI tree)

- Dump: `adb shell "uiautomator dump /sdcard/window_dump.xml"` — ≈2.5 s, ≈11 KB (lockscreen tree). Quoting mandatory (path trap above).
- Pull: `adb pull //sdcard/window_dump.xml .scratch/tmp/` — small files pull in ~10 ms; backgrounding only pays off for large files.
- **The XML is a single line.** Line-based reasoning is useless; extract with `rg -o`:
  - clickable targets with bounds: `rg -o 'text="[^"]*"[^>]*?clickable="true"[^>]*?bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' dump.xml`
  - all ids: `rg -o 'resource-id="[^"]+"' dump.xml | sort -u`
- Pair bounds with `adb shell input tap <x> <y>` to drive the UI programmatically.

## dumpsys / pm — filter or drown

Verified: `dumpsys activity` raw = 22,750 lines; the filtered lookup below = 2 lines.

| Want | Command |
|---|---|
| foreground activity | `adb shell dumpsys activity activities \| rg ResumedActivity` |
| focused window | `adb shell dumpsys window \| rg mCurrentFocus` |
| app version | `adb shell dumpsys package com.x \| rg versionName` |
| third-party packages | `adb shell pm list packages -3` (8) — vs all packages (252) |
| build prop | `adb shell getprop ro.build.version.sdk` |

## Long commands — background + log file

`adb install` (large APK), `am instrument -w` (full instrumentation run == full pytest run: same drain rules), `adb bugreport` (minutes, tens-of-MB zip — unzip then `rg`, never read it whole), `pull`/`push` of large files, gradle builds, `monkey`.
Pattern: `run_in_background` + output to `.scratch/tmp/<name>.log`, poll with `tail`, read back `rg`-filtered lines only.

## Cheat sheet

| Action | Command |
|---|---|
| launch | `adb shell am start -n com.pkg/.MainActivity` |
| deep link | `adb shell am start -a android.intent.action.VIEW -d "https://…"` |
| kill app | `adb shell am force-stop com.pkg` |
| clear data | `adb shell pm clear com.pkg` |
| tap / swipe / back | `adb shell input tap x y` / `input swipe x1 y1 x2 y2` / `input keyevent 4` |
| screenshot | `adb exec-out screencap -p > s.png` |
| app pid | `adb shell pidof com.pkg \| tr -d '\r'` |
| screen metrics | `adb shell wm size; adb shell wm density` |
| devices | `adb devices -l`; multi-device needs `-s <serial>` (or `-d` usb / `-e` emulator) |
