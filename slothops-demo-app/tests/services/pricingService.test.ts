import { calculateTotalWeight } from '../../src/services/pricingService';
import { getItemDetails } from '../../src/services/inventoryService';
import type { CartItem } from '../../src/services/inventoryService';

// Mock the inventoryService to isolate the pricingService logic
jest.mock('../../src/services/inventoryService', () => ({
  getItemDetails: jest.fn(),
}));

// Typecast the mock function for type safety
const mockedGetItemDetails = getItemDetails as jest.Mock<CartItem | null, [string]>;

describe('calculateTotalWeight', () => {

  beforeEach(() => {
    // Clear mock history and implementation before each test
    mockedGetItemDetails.mockClear();
  });

  // Test case that reproduces the original crash
  test('should correctly calculate weight for a cart with mixed physical and digital items', () => {
    const cartItemIds = ['req-101', 'req-102', 'req-103'];
    mockedGetItemDetails.mockImplementation((itemId: string) => {
      const mockInventory: Record<string, CartItem> = {
        "req-101": { id: "req-101", name: "Heavy Anvil", weight: { value: 50, unit: "kg" } },
        "req-102": { id: "req-102", name: "Digital Gift Card" }, // Item without weight
        "req-103": { id: "req-103", name: "Feather Pillow", weight: { value: 0.5, unit: "kg" } }
      };
      return mockInventory[itemId] || null;
    });

    const totalWeight = calculateTotalWeight(cartItemIds);
    expect(totalWeight).toBe(50.5);
  });

  // Edge case: cart with only items that have weight
  test('should correctly calculate weight for a cart with only physical items', () => {
    const cartItemIds = ['req-101', 'req-103'];
    mockedGetItemDetails.mockImplementation((itemId: string) => {
      const mockInventory: Record<string, CartItem> = {
        "req-101": { id: "req-101", name: "Heavy Anvil", weight: { value: 50, unit: "kg" } },
        "req-103": { id: "req-103", name: "Feather Pillow", weight: { value: 0.5, unit: "kg" } }
      };
      return mockInventory[itemId] || null;
    });

    const totalWeight = calculateTotalWeight(cartItemIds);
    expect(totalWeight).toBe(50.5);
  });

  // Edge case: cart with only items that do not have weight
  test('should return 0 for a cart with only digital (weightless) items', () => {
    const cartItemIds = ['req-102'];
    mockedGetItemDetails.mockImplementation((itemId: string) => {
      const mockInventory: Record<string, CartItem> = {
        "req-102": { id: "req-102", name: "Digital Gift Card" },
      };
      return mockInventory[itemId] || null;
    });

    const totalWeight = calculateTotalWeight(cartItemIds);
    expect(totalWeight).toBe(0);
  });

  // Edge case: empty cart
  test('should return 0 for an empty cart', () => {
    const cartItemIds: string[] = [];
    const totalWeight = calculateTotalWeight(cartItemIds);
    expect(totalWeight).toBe(0);
    expect(mockedGetItemDetails).not.toHaveBeenCalled();
  });

  // Edge case: item ID not found in inventory
  test('should ignore items that are not found in inventory', () => {
    const cartItemIds = ['req-101', 'non-existent-item'];
    mockedGetItemDetails.mockImplementation((itemId: string) => {
      const mockInventory: Record<string, CartItem> = {
        "req-101": { id: "req-101", name: "Heavy Anvil", weight: { value: 50, unit: "kg" } },
      };
      return mockInventory[itemId] || null;
    });

    const totalWeight = calculateTotalWeight(cartItemIds);
    expect(totalWeight).toBe(50);
  });
});
