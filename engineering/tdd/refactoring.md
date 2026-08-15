# Refactor Candidates

Loaded on demand by `/tdd` §4 (Refactor).

After TDD cycle, look for:

- **Duplication** → Extract function/class
- **Long methods** → Break into private helpers (keep tests on public interface)
- **Shallow modules** → Combine or deepen
- **Feature envy** → Move logic to where data lives
- **Primitive obsession** → Introduce value objects
- **Existing code** the new code reveals as problematic

> This is the curated short list for the moment right after a green cycle. The full smell set (12 Fowler smells, each with a fix) lives in the `/code-review` skill's Standards baseline — reach for it when reviewing a whole diff, not mid-loop.
