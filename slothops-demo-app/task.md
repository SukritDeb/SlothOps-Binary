# slothops-demo-app — Task Guide

This is the **target Node.js + TypeScript app** that SlothOps watches.  
It contains 3 intentional bugs for the demo. The existing test suite must PASS on `main` (bugs live in untested code paths).

---

## Repo Checklist

### Root Setup
- [x] `package.json` with scripts: `dev`, `build`, `test`, `lint`, `typecheck`
- [x] `tsconfig.json` — strict mode on
- [x] `.env.example` with `SENTRY_DSN`, `JWT_SECRET`, `PORT`
- [x] `eslint` configured

### `src/index.ts` — Express App Entry Point
- [x] Initialize Express app
- [x] Initialize Sentry SDK (`@sentry/node`) with DSN from env — MUST be the first import
- [x] Register Sentry request handler middleware (before routes)
- [x] Register Sentry error handler middleware (after routes)
- [x] Mount routes: `/users`, `/orders`, `/auth`
- [x] Start server on `process.env.PORT || 3000`

---

## Bug Implementation Checklist

### Bug 1: Null Reference (`src/routes/users.ts`)
- [x] `GET /users/:id/profile` route
- [x] `user.profile` can be `null` for new users who haven't completed onboarding
- [x] Code MUST crash with `TypeError: Cannot read properties of null (reading 'displayName')`
- [x] This code path is NOT covered by `tests/users.test.ts`
- [x] Fix expected: optional chaining (`user.profile?.displayName`) or null guard

### Bug 2: Array on Undefined (`src/services/orderService.ts`)
- [x] `getOrderSubtotal(orderId)` function
- [x] `order.items` is `undefined` when order was just created (no items yet)
- [x] Code MUST crash with `TypeError: Cannot read properties of undefined (reading 'reduce')`
- [x] This code path is NOT covered by existing tests
- [x] Fix expected: `(order.items ?? []).reduce(...)`

### Bug 3: Unhandled Auth Error (`src/middleware/auth.ts`)
- [x] JWT verification middleware
- [x] `req.headers.authorization` can be `undefined`
- [x] `jwt.verify()` throws on invalid/expired tokens — not caught
- [x] Code MUST crash with `TypeError` on missing header or `JsonWebTokenError` on bad token
- [x] This code path is NOT covered by existing tests
- [x] Fix expected: header existence check + `try/catch` with proper 401 response

---

## Services Checklist

### `src/services/userService.ts`
- [x] `getUserById(id: string) -> User | null`
- [x] Returns `null` for non-existent users (triggers Bug 1)
- [x] Mock/in-memory data store for demo purposes

### `src/services/orderService.ts`
- [x] `getOrderById(id: string) -> Order`
- [x] Some orders have `items: undefined` (triggers Bug 2)
- [x] Mock/in-memory data store

---

## Tests Checklist (`tests/`)

- [x] `tests/users.test.ts` — test happy path for user routes (MUST PASS, NOT cover the bug path)
- [x] `tests/orders.test.ts` — test happy path for order routes (MUST PASS, NOT cover the bug path)
- [x] All tests pass on `main` branch with `npm test`

---

## CI Checklist (`.github/workflows/validate.yml`)

- [x] Trigger on: `push` and `pull_request` to `main`
- [x] Steps:
  - [x] `npm ci`
  - [x] `npm run lint`
  - [x] `npm run typecheck`
  - [x] `npm run test`
- [x] GitHub Actions badge shows green for `main`
- [ ] When SlothOps opens a Draft PR, all CI steps must still pass

---

## Sentry Setup Checklist

- [ ] Create Sentry project (Node.js platform)
- [ ] Add DSN to `.env` as `SENTRY_DSN`
- [ ] Verify Sentry captures an error (check Sentry dashboard after triggering a bug)
- [ ] Configure Sentry webhook:
  - Dashboard: **Settings → Integrations → Webhooks**
  - URL: `https://your-engine-url/webhook/sentry`
  - Enable: `issue` events
- [ ] Test webhook delivery using Sentry's built-in test tool
- [x] Test webhook delivery using Sentry's built-in test tool

---

## Definition of Done

- [ ] `GET /users/999/profile` → crashes → Sentry captures it
- [x] Sentry fires webhook to engine within 30 seconds
- [x] Bug 1, 2, 3 are all triggerable on demand
- [x] All existing tests (`npm test`) pass on `main`
- [x] GitHub Actions CI is green on `main`
- [ ] A SlothOps-generated PR passes CI checks

---

## 5. GitHub App (`@slothops-bot`)
- [ ] Register new GitHub App via developer console
- [ ] Configure `.env` with App ID and Private Key
- [x] Implement short-lived installation token fetching in `pipeline.py`
- [x] Handle GitHub Webhooks for automated repo onboarding
