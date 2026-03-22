export interface CartItem {
  id: string;
  name: string;
  weight?: {
    value: number;
    unit: string;
  };
}

const mockInventory: Record<string, CartItem> = {
  "req-101": { id: "req-101", name: "Heavy Anvil", weight: { value: 50, unit: "kg" } },
  "req-102": { id: "req-102", name: "Digital Gift Card" }, // Missing weight object -> Root Cause
  "req-103": { id: "req-103", name: "Feather Pillow", weight: { value: 0.5, unit: "kg" } }
};

export function getItemDetails(itemId: string): CartItem | null {
  return mockInventory[itemId] || null;
}
