# Refactor Candidates

Loaded on demand by `/tdd` §4 (Refactor).

After GREEN, refactor only debt introduced or directly exposed by this change that obstructs
its correctness or clarity. These are diagnostic prompts, not mandatory transformations:

- **Duplication** → Extract function/class
- **Long methods** → Break into private helpers (keep tests on public interface)
- **Shallow modules** → Combine or deepen
- **Feature envy** → Move logic to where data lives
- **Primitive obsession** → Introduce value objects
- **Existing code** that prevents the requested behavior; report unrelated cleanup separately

> This is the curated short list for the moment right after a green cycle. The full smell set (12 Fowler smells, each with a fix) lives in the `/code-review` skill's Standards baseline. Reach for it when reviewing a whole diff, not mid-loop.
