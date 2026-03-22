import { getOrderById, getOrderSubtotal } from "../src/services/orderService";

describe("Order Service", () => {
  it("should return order details for an existing order", () => {
    const order = getOrderById("101");
    expect(order).not.toBeNull();
    expect(order?.status).toBe("processing");
  });

  it("should calculate correct subtotal for an order with items", () => {
    const subtotal = getOrderSubtotal("101");
    // p1 = 100*2=200, p5 = 50*1=50, Total = 250
    expect(subtotal).toBe(250);
  });

  it("should return null for non-existent orders", () => {
    const order = getOrderById("not_exist");
    expect(order).toBeNull();
  });

  it("should throw error getting subtotal for non-existent orders", () => {
    expect(() => getOrderSubtotal("not_exist")).toThrow("Order not found");
  });

  // Notice how NO test specifically tests order "999" starting with undefined items!
  // This validates the fact that standard test coverage often misses edge cases.
});
