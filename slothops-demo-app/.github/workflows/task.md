# .github/workflows/ — CI Configuration

---

## Checklist

### `validate.yml` — GitHub Actions CI
- [ ] Trigger on: `push` and `pull_request` targeting `main`
- [ ] Node.js version: 20
- [ ] Steps in order:
  - [ ] `npm ci` — clean install
  - [ ] `npm run lint` — ESLint
  - [ ] `npm run typecheck` — `tsc --noEmit`
  - [ ] `npm run test` — Jest
- [ ] All steps must be GREEN on `main` at all times
- [ ] When SlothOps opens a Draft PR, this CI must also be GREEN
- [ ] This is what judges see — the green checkmark on the bot's PR

---

## Why This Matters

The CI passing on a SlothOps-generated PR is the proof that:
1. The AI generated syntactically valid TypeScript
2. The AI didn't break existing functionality
3. The fix is safe to review and merge

This is the visual "wow moment" for the demo.
