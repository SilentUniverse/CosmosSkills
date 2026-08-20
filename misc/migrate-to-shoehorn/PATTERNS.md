# Shoehorn migration patterns

Loaded on demand by [migrate-to-shoehorn](SKILL.md) during the replacement pass.

### Large objects with few needed properties → `fromPartial()`

```ts
type Request = {
  body: { id: string };
  headers: Record<string, string>;
  cookies: Record<string, string>;
  // ...20 more properties
};

it("gets user by id", () => {
  // Only care about body.id but must fake entire Request
  getUser({
    body: { id: "123" },
    headers: {},
    cookies: {},
    // ...fake all 20 properties
  });
});
```

```ts
import { fromPartial } from "@total-typescript/shoehorn";

it("gets user by id", () => {
  getUser(
    fromPartial({
      body: { id: "123" },
    }),
  );
});
```

### `as Type` → `fromPartial()`

```ts
getUser({ body: { id: "123" } } as Request);
```

```ts
getUser(fromPartial({ body: { id: "123" } }));
```

### `as unknown as Type` → `fromAny()`

```ts
getUser({ body: { id: 123 } } as unknown as Request); // wrong type on purpose
```

```ts
getUser(fromAny({ body: { id: 123 } }));
```
