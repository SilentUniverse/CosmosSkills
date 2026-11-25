---
name: cpp-oop-style
description: >-
  Use when writing, editing, or reviewing C++ (.cpp/.h/.hpp/.cc/.cxx) or CMake. Enforces project conventions first, strict separation of abstract interfaces, data structs, and RAII/value types, modern type safety, and modular CMake targets.
---

# archibate C++ OOP Style

Write C++ like a senior systems engineer — clear seams, value safety, zero autocompleter slop.

## 1. Project conventions first

Existing codebase style, naming, ownership, error handling, and build setup (`.clang-format`,
`.clang-tidy`, CMake layout, Qt idioms inside Qt modules) override this skill. Apply these defaults
to new code where the project sets no convention; never restyle untouched code.

## 2. The one rule

> **Abstract class, data class, or value/resource type. Nothing else.**

Every introduced type belongs to exactly one kind — reject the muddy-middle concrete class mixing
private state, grab-bag methods, and free helpers:

- **Abstract class (behavior only):** pure-virtual `struct`, zero data members, `virtual ~T() = default;`.
  Concrete `struct FooImpl final : Foo` lives in `.cpp` (or minimally declared when stack-allocated)
  and returned via factory when hidden.
- **Data class (data only):** plain aggregate `struct` with public fields and designated initializers
  (`FooConfig{.size = 1.0f}`), no business logic, no trivial getters/setters.
- **Value / resource type:** concrete Regular/RAII type owning a resource or enforcing one invariant
  (`Money`, `Age::fromYears`, C-handle wrapper) with `private` representation and small total API.

## 3. Core defaults (apply on every C++ edit)

| AI-slop default | Required idiom |
|---|---|
| Concrete class mixing state + methods, or global + free helpers | Pure-virtual interface (`Dep *` borrowed, wired at composition root) **or** plain data `struct` |
| `void f(string n, int a, int p)` / `pair<bool, T>` | Named config `struct` (≥3 related args) and named result `struct` |
| `new` / `delete` / `new T[]` | `std::make_unique`, `std::vector<T>`, RAII; `shared_ptr` only for true shared ownership |
| `-1` / null / empty-string error sentinels | `std::optional<T>`, `std::expected<T, E>`, or named result struct |
| `enum Mode` + `switch (getType())` | Strategy/functor/State interface (open set) or `std::variant` + `std::visit` (closed set) |
| `class Foo`, `const T&`, `m_x`, `#ifndef` | `struct Foo`, East const (`T const &`), bare `camelCase` members, `#pragma once` |
| `Type x = v`, `Dog d("a", 1)`, `(T)x` | `auto const x = ...` or `Type const x{v}`, `auto d = Dog{"a", 1}` (`()` only for `initializer_list` disambiguation like `vector<int>(3)`), `explicit` ctors, checked `static_cast` / `std::in_range` |
| `!a && (b || c)` in boolean conditions | `not a and (b or c)` with explicit parens on mixed `and`/`or` (keep `!=` and bitwise ops symbolic) |

Keep functions focused (early return, ≤3 nesting levels, ≤24 lines where practical). Use `assert` /
`static_assert` for internal invariants only — never to validate external input. Keep CMake modular:
one target per module (`OBJECT` internal, `STATIC`/`SHARED` at real ABI/archive boundaries),
`include/<module>/` + `src/`, explicit `PRIVATE`/`PUBLIC`/`INTERFACE`, `CMakePresets.json` for
repeated profiles, and one CMake target per third-party dependency resolved at the composition root.

## 4. Load references on demand

Read only the reference matching the active task before designing or restructuring that surface:

- **Interfaces, polymorphism, DI, `Api`/`Spi`, factories, single-impl hiding, singletons & library models** →
  [class-design-patterns.md](references/class-design-patterns.md)
- **Data/value structs, `auto`/`const`/`{}`/`explicit`, cast ladder, integer widths & compiler flags** →
  [value-types-and-idioms.md](references/value-types-and-idioms.md)
- **Multi-module seams, compute vs I/O boundaries & agent harnesses** →
  [decoupled-modules.md](references/decoupled-modules.md)
- **Smart pointers, borrowed vs owned collaborators, Rule of Five & lifetime traps** →
  [ownership-lifetime.md](references/ownership-lifetime.md)
- **Recoverable vs fatal errors, `optional`/`expected` & result fallbacks** →
  [error-handling.md](references/error-handling.md)
- **RAII wrappers for opaque C handles (`error_category`, builders, scope guards)** →
  [wrapping-c-resources.md](references/wrapping-c-resources.md)
- **Template `Func` vs `std::function`, lambdas & capture lifetimes** →
  [functors-callbacks.md](references/functors-callbacks.md)
- **`concept` overloads, `if constexpr` gating, `std::variant` & forwarding** →
  [generics-compile-time.md](references/generics-compile-time.md)
- **Non-intrusive type erasure & C++17 wrapper patterns** →
  [type-erasure.md](references/type-erasure.md)
- **UTF-8, `filesystem::path` & Qt/platform text boundaries** →
  [text-encoding.md](references/text-encoding.md)
- **CMake project/target layout & presets** → [cmake-first-projects.md](references/cmake-first-projects.md)
- **Third-party dependencies, vendoring, SDKs & ABI mismatches** →
  [dependencies/router.md](references/dependencies/router.md)
- **Install, packaging, portable bundles, installers & Python wheels** →
  [deployment/router.md](references/deployment/router.md)
- **Diagnostic logging (`debug-instrumentation`) & controllable REPL/debug harnesses** →
  [debug-instrumentation.md](references/debug-instrumentation.md), [debug-harnesses.md](references/debug-harnesses.md)
- **Provenance & exemplar study sources** → [sources.md](references/sources.md)
