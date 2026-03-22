export interface OrderItem {
  id: string;
  productId: string;
  price: number;
  quantity: number;
}

export interface Order {
  id: string;
  userId: string;
  status: "pending" | "processing" | "shipped";
  items?: OrderItem[]; // Undefined when order is freshly created but empty
}

const mockOrders: Record<string, Order> = {
  "101": {
    id: "101",
    userId: "1",
    status: "processing",
    items: [
      { id: "i1", productId: "p1", price: 100, quantity: 2 },
      { id: "i2", productId: "p5", price: 50, quantity: 1 }
    ]
  },
  // Bug trigger: Order 999 was just created, items is undefined
  "999": {
    id: "999",
    userId: "2",
    status: "pending",
  }
};

export function getOrderById(id: string): Order | null {
  return mockOrders[id] || null;
}

import { getLoyaltyDiscount } from "./discountService";

export function getOrderSubtotal(orderId: string): number {
  const order = getOrderById(orderId);
  if (!order) throw new Error("Order not found");

  // order.items can be undefined for new orders. Default to an empty array to calculate subtotal.
  const total = (order.items || []).reduce((acc, item) => {
    return acc + (item.price * item.quantity);
  }, 0);

  return total;
}

/**
 * Calculate the final invoice total for an order.
 * Applies the user's loyalty discount to the subtotal.
 *
 * Call chain: orders.ts → calculateTotal() → getLoyaltyDiscount() → getUserById()
 */
export function calculateTotal(orderId: string): { subtotal: number; discount: number; total: number } {
  const order = getOrderById(orderId);
  if (!order) throw new Error("Order not found");

  const subtotal = getOrderSubtotal(orderId);

  // ✨ BUG 8 PROPAGATION ✨
  // This calls getLoyaltyDiscount with order.userId.
  // For order "101" (userId: "1") → works fine (user has loyalty.tier = "gold")
  // For order "999" (userId: "2") → CRASHES in discountService.ts
  //   because User "2" has no loyalty field at all.
  const discount = getLoyaltyDiscount(order.userId, subtotal);

  return {
    subtotal,
    discount,
    total: subtotal - discount,
  };
}
