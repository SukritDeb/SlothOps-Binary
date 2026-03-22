# src/routes/ — Demo App Routes

This folder contains Express route handlers. **Bugs 1 and 3 live here.**

---

## Checklist

### `users.ts` — Bug 1: Null Reference
- [ ] `GET /users/:id/profile` route defined
- [ ] Calls `userService.getUserById(id)` — returns `null` for ID `999` or any non-existent user
- [ ] Accesses `user.profile.displayName` WITHOUT null check → **intentional crash**
- [ ] This exact route must NOT be covered by `tests/users.test.ts`
- [ ] Sentry should capture: `TypeError: Cannot read properties of null (reading 'displayName')`
- [ ] Separate happy-path route (`GET /users/:id`) that IS tested and works fine

### `orders.ts` — Calls Into Bug 2 (service layer)
- [ ] `GET /orders/:id` route defined
- [ ] Calls `orderService.getOrderSubtotal(id)` — this crashes when `order.items` is undefined
- [ ] Route itself shouldn't add null checks (bug must stay in service layer)
- [ ] This code path must NOT be covered by `tests/orders.test.ts`
