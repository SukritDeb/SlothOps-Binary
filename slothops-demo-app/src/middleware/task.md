# src/middleware/ — Demo App Middleware

---

## Checklist

### `auth.ts` — Bug 3: Unhandled Auth Error
- [ ] JWT verification middleware exported as `verifyAuth`
- [ ] Reads `req.headers.authorization`
- [ ] Calls `.split(' ')[1]` on the header value — crashes if header is `undefined`
- [ ] Calls `jwt.verify(token, process.env.JWT_SECRET)` WITHOUT try/catch — throws on bad/expired token
- [ ] This middleware is applied to a route that is NOT covered by tests
- [ ] Sentry should capture the unhandled `TypeError` or `JsonWebTokenError`
- [ ] Fix expected:
  ```typescript
  if (!req.headers.authorization) return res.status(401).json({ error: 'Missing token' });
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET!);
    // ...
  } catch (err) {
    return res.status(401).json({ error: 'Invalid token' });
  }
  ```
