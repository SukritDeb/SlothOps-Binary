# src/services/ — Demo App Services

Business logic layer. **Bug 2 lives in `orderService.ts`.**

---

## Checklist

### `userService.ts`
- [ ] `getUserById(id: string): User | null`
- [ ] Returns `null` for unknown user IDs (triggers Bug 1 in the route layer)
- [ ] Returns a `User` object where `profile` is `null` for new/incomplete users
- [ ] In-memory mock data — no real DB needed

### `orderService.ts` — Bug 2: Array on Undefined
- [ ] `getOrderSubtotal(orderId: string): number`
- [ ] Some orders have `items: undefined` (e.g., newly created with no items yet)
- [ ] Code calls `order.items.reduce(...)` WITHOUT null check → **intentional crash**
- [ ] `TypeError: Cannot read properties of undefined (reading 'reduce')`
- [ ] Fix expected: `(order.items ?? []).reduce((sum, item) => sum + item.price * item.quantity, 0)`
- [ ] In-memory mock data for demo purposes
