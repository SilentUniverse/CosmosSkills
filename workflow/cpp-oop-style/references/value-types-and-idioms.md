# Type-Rich Data, Value Idioms, Casts & Compiler Hygiene

Loaded on demand from [`SKILL.md`](../SKILL.md) when designing data/value structs, local variable
declarations, `const` / initialization / cast / integer rules, invariants, or compiler warning flags.

## Type-rich data classes & signature clarity

Make illegal states unrepresentable and declarations self-explanatory from names and types alone:

- **Bundle ≥3 related parameters** into a named config `struct` with designated initializers:
  `foo({.name = "x", .age = 24})`.
- **Return named structs**, never `std::pair` or `std::tuple` (`result.success`, not `result.first`).
- **Nullable returns use `std::optional<T>`** (or `std::expected<T, E>` / result struct when error
  reasons matter; see [error-handling.md](error-handling.md)) — never `-1`, empty string, or raw
  null sentinels.
- **Don't wrap always-present fields in `optional<T>`**; use `std::variant` or distinct types for
  real either/or choices.
- **`enum class : uint8_t` (explicit underlying width)** for flags/states; wrap non-interconvertible
  primitives (`Duration`, `FileHandle`, `UserId`) in strong single-member structs or scoped enums,
  and use `std::chrono` for time/durations.
- **Non-owning views for inputs:** `std::span<T const>` and `std::string_view` instead of `(ptr, len)`.
- **Plain data stays an aggregate `struct`** with public fields and no boilerplate constructors or
  getters/setters. Encapsulation and getters earn their place only inside a **value/resource type**
  guarding an invariant.
- **Name constructors by intent:** use `static` factories (`Angle::fromDegrees(x)`,
  `Angle::fromRadians(x)`) when construction modes share types or differ in meaning; rename
  ambiguous methods (`Process::isRunning()`, not `Process::check()`).

## Naming & header layout

- **Members:** bare `camelCase` — no `m_` prefix, no trailing `_` (trailing `x_` only on a
  ctor/setter parameter that shadows member `x`).
- **Types:** `PascalCase`; **methods/members:** `camelCase`; **constants:** `kPascalCase`;
  **predicates:** `shouldRetry()`, `canFlush()`, `isReady()`.
- **Headers:** one concept per small header; `#pragma once`; forward-declare in headers and
  `#include` in `.cpp`; share header definitions with `inline`, never `static`.
- **Always `struct`, never `class`**, even with `private:` / `protected:` sections — public surface
  leads at the top of the type.
- **East const everywhere:** `T const &`, `T const *`, `T const *const`.

## Local variables: `auto` vs named receiving type

Use one of two forms (adding `const` by default):

```cpp
auto const worker = std::make_unique<Worker>(config);
State const state{machine.state()};
```

- When passing constructor arguments, put the type on the RHS: `auto dog = Dog{"George", 10};`.
- Never write `Type x = rhs`, `Type x(rhs)`, or uninitialized `Type x`; `{}` rejects implicit
  narrowing at compile time (`std::size_t const count{fetchCount()};`).
- Range-for: `for (auto const &item : items)` to read, `for (auto &item : items)` to mutate,
  `for (auto const &[k, v] : map)` for maps.

## The `const` idiom

- **Almost Always Const:** `auto const x = ...;` unless reassigned or moved from; prefer new
  `const` bindings over mutating reuse outside loop accumulators.
- **Pass-by-value parameters:** mark `T const` in definitions to freeze local bindings; **never
  return `T const` by value** and leave locals non-`const` when moving ownership out.
- **Query methods:** mark every non-mutating member function `const` on both interfaces and
  overrides; return `const` views unless mutation is part of the contract.
- **`mutable`:** strictly for logical constness (mutexes, caches), never to hide state mutation.

## Boolean expressions, `{}` initialization & `explicit`

- **Boolean tokens:** prefer `not`, `and`, `or` in boolean conditions; parenthesize mixed `and`/`or`;
  keep `!=` and bitwise operators (`&`, `|`, `^`, `~`) symbolic; never use `not_eq`/`bitand`/`xor`
  or rewrite `T &&` rvalue syntax or third-party code.
- **Brace initialization (`{}`):** prefer `Dog{"George", 10}` over `Dog("George", 10)` when they
  call the same constructor. Use `()` only when `{}` selects a different `initializer_list`
  overload (`std::vector<int>(3)` = three zeros vs `std::vector<int>{3}` = `{3}`).
- **`explicit` by default** on single- and multi-argument constructors; allow implicit conversion
  only for lossless, unsurprising domain extensions (e.g. `BigInt(std::int32_t)`).

## Cast ladder & arithmetic types

- **Known-safe constants:** `{}` (`std::uint8_t{42}`).
- **Runtime integer conversion:** check bounds (`std::in_range<Dst>(v)` in C++20 or
  `numeric_limits`), then `static_cast`.
- **Float → int:** reject non-finite and out-of-range values and choose `floor`/`ceil`/`round`/truncation
  explicitly before `static_cast`.
- **Representation cast:** `std::bit_cast` (or `std::memcpy` + `static_assert` in C++17) on
  trivially-copyable equal-size types; never `reinterpret_cast` a byte buffer to a packed struct.
- **Polymorphic downcast:** prefer virtual dispatch; use `dynamic_cast` at checked boundaries and
  `static_cast` only beside an `assert`-backed invariant.
- **Ban C-style casts `(T)x`**, avoid `reinterpret_cast` except required `uintptr_t` round-trips,
  and avoid `const_cast` except read-only legacy C APIs.
- **Integers:** exact-width (`std::int32_t`, `std::uint8_t`) for wire/file/ABI/SIMD; `int` for
  ordinary local signed math; `size_type`/`std::size_t` for indexing and `std::ptrdiff_t` for
  signed deltas; avoid bare `long` (LP64 vs LLP64); write `3.14f` for `float` literals.

## Assertions & construction as validation

- Use `static_assert` for compile-time assumptions (e.g. signedness of differences) and `assert`
  for internal invariants (`NDEBUG` strips `assert` — never use it on external I/O or recoverable
  errors).
- Encode single-value or multi-field invariants inside a value type with a `private` `explicit`
  constructor and a `static` `optional`/`expected` factory (`Age::fromYears(n)`), so downstream
  aggregates (`UserConfig`) only ever hold already-validated values.

## Function size & compiler hygiene

- Keep functions single-responsibility, early-return, ≤3 nesting levels, ≤24 lines, ≤80 columns.
- Enforce rules via compiler flags where the project permits:
  `-Wall -Wextra -Weffc++ -Werror=return-type -Werror=uninitialized -Werror=suggest-override -Wzero-as-null-pointer-constant -Wold-style-cast -Werror=vla -Wnon-virtual-dtor -Wdelete-non-virtual-dtor -Wconversion -Wsign-compare -Werror=unused-result`
  (plus `-D_GLIBCXX_DEBUG` uniformly across all linked TUs in debug builds).
