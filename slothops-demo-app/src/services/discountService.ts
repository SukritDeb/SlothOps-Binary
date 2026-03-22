import { getUserById } from "./userService";

/**
 * Calculate the loyalty-based discount for a given user.
 *
 * Looks up the user's loyalty tier and applies a percentage discount
 * to the provided subtotal.
 */
export function getLoyaltyDiscount(userId: string, subtotal: number): number {
  const user = getUserById(userId);
  if (!user) return 0;

  // ✨ BUG 8 CRASH SITE ✨
  // Assumes every user has a `loyalty` object. User "2" does NOT.
  // Throws: TypeError: Cannot read properties of undefined (reading 'tier')
  //
  // The fix is NOT just adding ?. here — the real fix requires:
  //   1. userService.ts → make loyalty always present or properly typed
  //   2. This file → guard for missing loyalty
  //   3. orderService.ts → handle zero discount gracefully
  const tier = (user as any).loyalty.tier;

  const rates: Record<string, number> = {
    gold: 0.15,
    silver: 0.10,
    bronze: 0.05,
  };

  return subtotal * (rates[tier] || 0);
}
