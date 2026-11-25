# Class Design, Composition & Dependency Injection

Loaded on demand from [`SKILL.md`](../SKILL.md) when designing C++ interfaces, class hierarchies,
polymorphic dispatch, dependency injection, singletons, or selecting libraries to imitate.

## Virtual functions: two distinct jobs

Reach for `virtual` whenever either job earns an interface:

1. **Dispatch / dependency injection** — one shared caller works across subtypes it doesn't know,
   replacing type-tag switches (`switch (getType())`, `if (type == Dog)`). Adding a subtype touches
   no existing branch:

   ```cpp
   void feed(Animal *a) { puts("feeding"); a->speak(); puts("done"); }
   ```

2. **Implementation hiding** — the pure-virtual interface lives in a small header; the concrete
   `…Impl final` lives in the `.cpp`. Worthwhile even with a single implementation when it gives a
   compile firewall (heavy/third-party headers stay out of public headers), a clean ABI boundary, or
   a test seam.

Avoid only the *empty* interface: a `virtual` where callers already hold the concrete type, there is
one implementation, and you gain no hiding, seam, or ABI benefit.

## Abstraction escalation ladder

Escalate only as far as duplication demands: repeated value → variable; repeated logic → function;
clump of arguments → struct; shared state+behavior → class; fixed set of variants → `enum class`;
fixed set of types → `std::variant`; open set of behaviors → `virtual` interface. Resolve closed
compile-time type sets via `std::variant` or `concept`-constrained overloads (see
[generics-compile-time.md](generics-compile-time.md)), never an `if constexpr` type-switch.

## Interface discipline

- **One interface, one responsibility.** Never mix concerns (e.g. IO and computation) in one
  abstract class — split into orthogonal interfaces and compose in a high-level function:

  ```cpp
  struct Inputer { virtual ~Inputer() = default; virtual std::optional<int> fetch() = 0; };
  struct Reducer { virtual ~Reducer() = default; virtual int init() = 0; virtual int add(int, int) = 0; };
  int reduce(Inputer *in, Reducer *r);
  ```

- **Duty class breakdown.** When a class accumulates orthogonal method clusters, extract a focused
  duty interface (e.g. `Paintable::getPainter()` returning `std::unique_ptr<Painter>` with
  `CanvasPainter` private inside `Canvas.cpp`).
- **Template Method (non-virtual public wrapper, protected `virtual do_xxx`).** Public methods own
  contracts and ergonomic overloads; subclasses override only raw primitives (`std::pmr::memory_resource`
  idiom):

  ```cpp
  struct Converter {
      virtual ~Converter() = default;
      void process(std::string_view sv) { do_process(sv.data(), sv.size()); }
      void process(char const *s)       { do_process(s, std::strlen(s)); }
  protected:
      virtual void do_process(char const *s, size_t n) = 0;
  };
  ```

- **Strategy vs Template Method.** Multiple independent behaviors on one object → injected
  *Strategy* interfaces (stateless single axis → functor; stateful or multi-axis → strategy object).
  One behavior reading the object's own fields → *Template Method*.
- **Thin virtual core, fat non-virtual API.** Keep only primitives `virtual` (`do_read`, `do_write`,
  `do_seek`); build convenience methods (`getline`, `flush`) non-virtually on top.
- **Dynamic vs static polymorphism for DRY.** ≥2–3 paths sharing a concept: open/extensible set →
  abstract class (`Path const &` / `Path *` param, `std::unique_ptr<Path>` owned); closed fixed set →
  `std::variant` data/value wrapper (`Brush const &` param, `Brush` value). Avoid ad-hoc overload
  sets or templates for domain polymorphism unless required by metaprogramming or measured hot paths.

## Composition over subclass multiplication

- **Adapter:** wrap an interface and return the same interface to add one orthogonal capability.
- **State as class:** implement a `State` interface instead of `enum + switch`.
- **Component:** hold `std::vector<std::unique_ptr<Component>>`; never use multiple inheritance of
  behavior.
- **CRTP:** auto-implement boilerplate virtuals (`clone`, `accept`) in a `template <class D> struct Impl : Base` mixin.
- **Visitor / double-dispatch:** use `accept`/`visit` when behavior depends on two types instead of
  querying `getType()`.
- **Flyweight / Proxy:** hoist shared heavy immutable data (textures, tables) into a `shared_ptr`
  collaborator; keep per-instance fields local and forward (`sprite->draw(position)`).

## Header hygiene, factories & single-implementation hiding

Put the pure-virtual interface and factory declaration in a small header; keep `FooImpl final` and
heavy `#include`s inside `.cpp`:

```cpp
struct Widget {
    virtual ~Widget() = default;
    virtual void draw() = 0;
};
std::unique_ptr<Widget> makeWidget(WidgetConfig const &cfg);

struct WidgetImpl final : Widget {
    heavy::thirdparty::Object object;
    explicit WidgetImpl(WidgetConfig const &cfg);
    void draw() override;
};
std::unique_ptr<Widget> makeWidget(WidgetConfig const &cfg) {
    return std::make_unique<WidgetImpl>(cfg);
}
```

Prefer this over classic value-semantic PIMPL: it provides the compile firewall *plus* a test fake
or multi-backend link seam (one factory definition per backend directory).

## Command/callback pairs (`Api` / `Spi`)

For subsystems with inversion of control, split inbound commands (`Api`) from outbound events
(`Spi`); the owner implements `Spi`, borrows `Api`, and wires `api->setSpi(this)`:

```cpp
struct PlayerSpi { virtual ~PlayerSpi() = default; virtual void onTrackEnded() = 0; };
struct PlayerApi {
    virtual ~PlayerApi() = default;
    virtual void setSpi(PlayerSpi *spi) = 0;
    virtual void play(Track const &t) = 0;
};
```

## Singleton encapsulation

Prefer injection from the composition root. For a genuinely process-wide subsystem, hide the
constructor, delete copy/move, and define `static Game &instance()` in `.cpp` (`static Game inst;`).
Header-only singletons must be `inline` (never `static`) and still duplicate across Windows DLLs.

## Dependency injection rules

- **Inject abstractions, never concrete types**, into high-level functions and classes.
- **Inject a factory (`virtual unique_ptr<Product> create()`), not a pre-made product**, when the
  callee creates multiple instances over time.
- **Wire everything in one composition root** (`main.cpp` or setup entry); production and tests
  differ only in which factories the root calls.
- **Collaborators are borrowed (`Dep *` or `Dep const &`), never owned** by the injectee; see
  [ownership-lifetime.md](ownership-lifetime.md).

## Pragmatics & exemplar APIs

- **Don't pre-abstract internal one-offs.** Wait for a real second implementation unless you need a
  compile firewall, ABI boundary, or test seam.
- **Measured hot paths** may replace virtual/`std::function` with template `Func`
  ([functors-callbacks.md](functors-callbacks.md)) or data-oriented batches/SIMD paired with a
  reference test and benchmark.
- **Imitate:** `fmt` / `std::format` (compile-time type safety), `std::ranges` (composable
  adaptors), `magic_enum`, `nlohmann-json`, `tl::expected` / `std::expected`, `structopt`
  (struct-as-API).
- **Use when needed, never imitate the style of:** `poco` (raw `new` Java-style OOP),
  `rapidjson`/`jsoncpp` (untyped trees / SAX mazes), pre-RAII C APIs (`tinyxml2`, legacy OpenCV,
  `stb`). Keep Qt idioms (`QObject` parent ownership, `m_` members, signals/slots) strictly inside
  Qt-bound code.
