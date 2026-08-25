# Good and Bad Tests

Loaded on demand by `/tdd` when writing tests.

## Existing coverage (before writing any new test)

Identify the project's test convention from `docs/agents/domain.md`. If absent, infer from
project config files (`pytest.ini` / `pyproject.toml`, `package.json` test script,
`build.gradle` `testOptions`) and ask the user to confirm. Then suggest writing it into
`domain.md` so future runs skip this step. *(autonomous mode: adopt the inferred convention,
note it in `### 完成`)*

For each AC in the issue, find existing coverage. Drain `-p`: the brief carries the
**tests-so-far manifest**. Check AC against it; scan the filesystem only for what it can't
show. Serial drain: earlier issues' `### 完成` blocks are already in context. Interactive: scan
directly. Report covered vs uncovered briefly; record covered ACs in the `### 完成` block's
跳过的 AC field.

## Per-cycle checklist

```
[ ] Test describes behavior, not implementation
[ ] Test uses public interface only
[ ] Test would survive internal refactor
[ ] Code is minimal for this test
[ ] No speculative features added
```

## Good Tests

**Integration-style**: Test through real interfaces, not mocks of internal parts.

```typescript
// GOOD: Tests observable behavior
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

Characteristics:

- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

## Bad Tests

**Implementation-detail tests**: Coupled to internal structure.

```typescript
// BAD: Tests implementation details
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

Red flags:

- Mocking internal collaborators
- Testing private methods
- Asserting on call counts/order
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of interface

```typescript
// BAD: Bypasses interface to verify
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: Verifies through interface
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

**Tautological tests**: the assertion recomputes the expected value the same way the code does, so it passes by construction and can never disagree with the code. Zero confidence. Distinct from the implementation-coupling smell above. Expected values must come from an *independent* source of truth: a known-good literal, a worked example, or the spec.

```typescript
// BAD: asserts the code against itself
test("applyDiscount computes the discounted price", () => {
  const price = 100, rate = 0.2;
  expect(applyDiscount(price, rate)).toBe(price - price * rate); // same formula as the impl
});

// GOOD: expected value from an independent worked example
test("applyDiscount takes 20% off 100 → 80", () => {
  expect(applyDiscount(100, 0.2)).toBe(80); // known-good literal
});
```
