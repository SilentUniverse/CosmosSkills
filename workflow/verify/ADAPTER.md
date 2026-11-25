# Verify — control adapter contract

Loaded when a capability drives a running UI, device or desktop instance: browser, Electron app,
simulator or native application. Every such adapter satisfies this contract; platform recipes are
in [DRIVERS.md](DRIVERS.md).

## Capability report first

Before touching any target, the adapter prints one capability report. For each operation below it
states `available` with the concrete mechanism and version (for example `CDP Input.dispatchMouseEvent
on 127.0.0.1:<port>`), or `missing` with the reason: not installed, permission not granted, disabled
by a build flag or fuse, unsupported on this host. The scenario declares the operations it needs.
When a needed operation is `missing`, the run exits nonzero before launch and names the gap.

The adapter never substitutes a weaker mechanism to keep going: an internal setter for a click, a
screenshot for a recording, a source preview for the fixed candidate. It never installs, upgrades,
enables or grants anything. Probes are read-only: version and help output, configuration reads,
existing permission queries. A probe that would raise an OS permission prompt reports `unknown`,
which counts as missing.

## Operations

| Operation | Contract |
|---|---|
| Launch and confirm | Start an instance the run owns (fresh profile, data directory or device) and wait on a concrete readiness condition with a bound. Then read the target's identity: process id, bundle or app id, version or build hash, and the window, page or device the operations address. Stop when the identity differs from the fixed candidate or the target is a pre-existing user instance. |
| Operate | Real user input on the public path: pointer, keyboard, touch, menu or accessibility action on stable handles (accessibility id, test id, role and name). Use coordinates only when no handle exists, and check them against a screenshot. Setup and fault injection (deep links, permission grants, push payloads, seeded data) are separate labeled commands and never count as the user step. |
| Inspect | Read-only queries of visible state, accessibility tree, DOM, logs or app data. An inspection never clicks, focuses, scrolls or writes; a query that needs a state change is an operation. |
| Screenshot | Capture the addressed window or device at a declared size, scale and theme into the run's evidence location, and record which state it shows. |
| Record | Start before the first user step; stop through the recorder's finalize path (for example SIGINT) so a failed run still leaves a playable file. A recording shows behavior; assertions decide pass or fail. |
| Recover | Inspect an interrupted operation and restore owned state. Never repeat a write whose outcome is unknown. |
| Clean up | After evidence is written, stop only the handles this run acquired (process tree, device, profile, port), in reverse order. Report anything left and how to recover it. Never close or reset a pre-existing instance. |

Each run writes one report to a fresh run location: the capability report, target identity, every
step with its kind (setup, operate, inspect), observations, assertion results, evidence paths and
the cleanup result. The exit status follows the first missing capability or failed assertion. A run
without assertions is not a pass.

## MCP and interactive sessions

MCP servers, harness browser-use or computer-use tools and manual sessions are for exploration and
diagnosis: finding handles, reaching a state, reading a failure. They are not final proof. Final
proof is a repository script that the next executor reruns from a clean checkout. It launches,
operates, asserts and cleans up through drivers the project's setup declares, with no conversation
or MCP session involved. Port what exploration learned into that script and run it. A transcript,
an MCP tool result or a screenshot that "looks right" stays diagnostic evidence.
