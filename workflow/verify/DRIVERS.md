# Verify — driver recipes

Starting points for [control adapters](ADAPTER.md) on three surfaces. Prefer the project's existing
driver (Playwright, XCUITest, Appium, FlaUI) when it already reaches the surface. Confirm each command
against the installed tool's help before writing it into project instructions, and record only
commands that ran.

## Electron (CDP)

- **Launch:** start the packaged binary, or the project's dev launcher, with
  `--remote-debugging-port=<free port>` and an isolated `--user-data-dir=<run dir>`; poll
  `http://127.0.0.1:<port>/json/version` until it answers. A project on Playwright can use
  `_electron.launch({ executablePath, args })` (experimental API), which adds main-process access.
- **Confirm:** `/json/version` reports the browser build; `/json/list` lists targets. Select the `page`
  target by URL or title, never by position. Read the app version in the main process through
  Playwright `electronApp.evaluate(({ app }) => app.getVersion())`, or through `--inspect` when the
  `EnableNodeCliInspectArguments` fuse is on (`npx @electron/fuses read --app <path>`). A production
  build can disable both; report that as missing.
- **Operate:** `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent` and `Input.insertText` at element
  boxes resolved from the DOM; Playwright `click`, `fill` and `press` use the same input path.
  `Runtime.evaluate("el.click()")` is setup or injection, not a user step.
- **Inspect:** `Runtime.evaluate` with side-effect-free expressions (`throwOnSideEffect: true`),
  `DOM.getDocument` and `DOM.querySelector`, `Accessibility.getFullAXTree`; console and exceptions
  through `Runtime.consoleAPICalled` and `Runtime.exceptionThrown`, failed requests through
  `Network.loadingFailed`. Check CSP and main, preload and renderer ownership for external resources.
- **Screenshot and record:** `Page.captureScreenshot` per page target, with
  `Emulation.setDeviceMetricsOverride` fixed for comparisons; Playwright `recordVideo`, or
  `Page.startScreencast` frames assembled after the run.
- **Outside CDP:** native menus, file dialogs, tray icons and notifications. Drive and record them with
  the desktop native driver below, or report them as missing.
- **Clean up:** stop the process tree by the pid captured at launch, then remove the run's user-data
  directory.

## iOS Simulator

- **Launch:** create a dedicated device (`xcrun simctl create <name> <device type> <runtime>`), boot it
  and wait (`xcrun simctl bootstatus <udid> -b`), then `xcrun simctl install <udid> <App.app>` and
  `xcrun simctl launch <udid> <bundle id>`. Address the device by UDID; `booted` is ambiguous when
  several devices run.
- **Confirm:** `xcrun simctl list devices --json` for state and runtime; bundle id and version from the
  built app's `Info.plist` (`/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString'`);
  `xcrun simctl get_app_container <udid> <bundle id>` shows the app is installed on that device.
- **Operate:** simctl has no tap or typing. Use an XCUITest UI-test target
  (`xcodebuild test -destination 'id=<udid>' -only-testing:<target>/<case>`) with accessibility
  identifiers, or `idb ui tap` and `idb ui text` when idb is installed. idb taps take points, and the
  point scale has been reported wrong on 3x devices, so check a tap against a screenshot.
  `simctl openurl`, `simctl privacy`, `simctl push` and `simctl location` are setup or fault
  injection.
- **Inspect:** XCUITest queries, `idb ui describe-all`, `xcrun simctl spawn <udid> log stream
  --predicate '<predicate>'`, and files in the app container.
- **Screenshot:** `xcrun simctl io <udid> screenshot <path>`; set `xcrun simctl status_bar <udid>
  override` for stable captures.
- **Record:** run `xcrun simctl io <udid> recordVideo --codec h264 <path>` in the background and stop it
  with SIGINT; SIGKILL leaves an unplayable file.
- **Clean up:** `simctl terminate`, `simctl shutdown` and `simctl delete` for the device this run
  created, and nothing else.

## Desktop native

Drive the application through the platform accessibility API. Coordinates and synthetic window-system
events are a last resort.

- **macOS:** run the built bundle's executable (`<App>.app/Contents/MacOS/<name>`) and keep its pid;
  read `CFBundleIdentifier` and `CFBundleShortVersionString` from its `Info.plist`. Operate and inspect
  through a macOS XCUITest UI-test target or an Accessibility (AXUIElement) client such as `osascript`
  with System Events; both need the Accessibility permission for the host process. Capture with
  `screencapture -x -l <window id> <path>` and record with `screencapture -v` or ffmpeg
  `avfoundation`; both need the Screen Recording permission. A missing permission is a missing
  capability; never click through a permission prompt.
- **Windows:** UI Automation through FlaUI, pywinauto (`backend="uia"`) or the Appium Windows driver,
  addressing elements by AutomationId. Capture through the driver; record with ffmpeg `gdigrab`. It
  needs an interactive desktop session; a service session has no UI.
- **Linux:** AT-SPI (dogtail, pyatspi) to operate and inspect. `xdotool` works only on X11, and many
  toolkits ignore synthetic events; Wayland compositors block it, so use the toolkit's test driver or
  report the gap. Capture and record with ffmpeg `x11grab` on X11; on Wayland use the compositor's
  tools (`grim`, `wf-recorder` on wlroots).
- **Clean up:** stop the launched process tree and remove its temporary profile; never close windows
  of an instance the run did not start.
