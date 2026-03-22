export interface User {
  id: string;
  email: string;
  profile: {
    displayName: string;
    avatarUrl: string;
  } | null; // Null if onboarding is incomplete
  loyalty?: {
    tier: "gold" | "silver" | "bronze";
    points: number;
  };
}

const mockUsers: Record<string, User> = {
  "1": { id: "1", email: "alice@example.com", profile: { displayName: "Alice", avatarUrl: "" }, loyalty: { tier: "gold", points: 4200 } },
  // ✨ ROOT CAUSE of Bug 8: User "2" never enrolled in the loyalty program.
  // loyalty field is completely absent — not null, UNDEFINED.
  // Crashes 3 files away in discountService.ts → getLoyaltyDiscount()
  "2": { id: "2", email: "bob@example.com", profile: { displayName: "Bob", avatarUrl: "" } },
  // Bug trigger: User 999 has not completed onboarding
  "999": { id: "999", email: "incomplete@example.com", profile: null },
};

export function getUserById(id: string): User | null {
  return mockUsers[id] || null;
}
