# Combined execution-domain model

Load this reference only when changing the combined parser or its policy. It defines what counts as
host-executed code; [../README.md](../README.md) owns measurements and retained implementation gaps.

## Host code and data

- Quoted remote or device commands are data: `ssh host "git reset --hard"` and `adb shell "ps -A |
  grep system"` do not block.
- `$(...)` and backtick substitutions are host code, including inside double quotes. `echo "$(grep
  x file)"` blocks.
- `[[ ... ]]` interiors are data except for substitutions. Array literal values, function names,
  comments, case patterns, and heredoc bodies are also data; case bodies and pipelines on heredoc
  opener lines remain live host code.
- A host pipeline resumes after remote data. In `adb logcat -d | grep x`, `grep` is a host command
  and blocks.
- Redirect targets belong to the shell, not to the native executable. `python x.py > /tmp/out` is
  allowed while `python x.py /tmp/out` is an executable argument and may block on MSYS.

## Command position

Normalize command basenames, so `/usr/bin/git` and `/usr/bin/grep` retain their meaning. Walk through
shell keywords, variable assignments, grouping, and supported wrappers such as `sudo`, `env`,
`nohup`, `nice`, `timeout`, `time`, `xargs`, `stdbuf`, `watch`, `command`, `builtin`, `setsid`, and
`exec`. Consume each wrapper's value-taking flags before selecting the command word. Text passed to
`echo` is not a command, and `command -v grep` is an inspection rather than a `grep` invocation.

Static quoted payloads passed to local `bash`, `sh`, or `zsh` with `-c`, and to `eval`, are rescanned
with a depth cap. Dynamic payloads and dynamic command words pass because the static parser cannot
classify them reliably.

## MSYS path domain

The path tier activates for MSYS or Cygwin. An explicit non-MSYS `OSTYPE`, including WSL, disables
it; when `OSTYPE` is absent, the hook falls back to the host platform. Tests may force the tier with
`GUARD_SHELL_FORCE_MSYS=1`. Static local-shell payloads inherit the same tier. macOS and Linux keep
valid POSIX paths.

Block POSIX path arguments passed to native Windows executables because MSYS rewrites them before
the target sees them. Also block unquoted Android-root `sdcard`, `data`, or `system` paths passed to
`adb` or `fastboot`. Quoted device commands, double-slash remote paths for pull or push,
and `MSYS_NO_PATHCONV=1` with Windows-form local paths remain valid. Host-side filters after Android
commands still use modern host tools.
