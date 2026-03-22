import { Router } from "express";
import { getOrderById, getOrderSubtotal, calculateTotal } from "../services/orderService";
import { requireAuth } from "../middleware/auth";

const router = Router();

// Uses our buggy auth middleware
router.get("/:id", requireAuth, (req, res) => {
  const order = getOrderById(req.params.id as string);
  if (!order) {
    return res.status(404).json({ error: "Order not found" });
  }
  res.json(order);
});

// Calculate subtotal
router.get("/:id/subtotal", (req, res) => {
  try {
    const subtotal = getOrderSubtotal(req.params.id);
    res.json({ orderId: req.params.id, subtotal });
  } catch (err: any) {
    if (err.message === "Order not found") {
      return res.status(404).json({ error: "Order not found" });
    }
    // Let other errors (like our TypeError bug) bubble up to Sentry
    throw err;
  }
});

// ✨ BUG 8 TRIGGER ✨
// Deep call chain: orders.ts → orderService.calculateTotal → discountService.getLoyaltyDiscount → userService.getUserById
// Order "101" (userId "1") works fine — User "1" has loyalty.tier = "gold"
// Order "999" (userId "2") CRASHES — User "2" has no loyalty at all
router.get("/:id/invoice", (req, res) => {
  try {
    const invoice = calculateTotal(req.params.id);
    res.json({
      orderId: req.params.id,
      ...invoice,
      message: "Invoice generated successfully",
    });
  } catch (err: any) {
    if (err.message === "Order not found") {
      return res.status(404).json({ error: "Order not found" });
    }
    // Let TypeError from deep chain bubble up to Sentry
    throw err;
  }
});

router.post("/receipt", (req, res) => {
  const payload = req.body;
  // ✨ BUG: SaaS DEMO VULNERABILITY ✨
  // Throws TypeError: Cannot read properties of undefined (reading 'toUpperCase')
  const formattedId = payload.receiptId.toUpperCase();
  res.json({ id: formattedId });
});

router.post("/:id/refund", (req, res) => {
  const order = getOrderById(req.params.id as string);
  if (!order) {
    return res.status(404).json({ error: "Order not found" });
  }

  // Simulate calling a payment gateway that returns a response object
  const gatewayResponse: any = {
    status: "approved",
    transaction: null, // Gateway returned null transaction on partial refunds
  };

  // ✨ BUG 8: NESTED NULL TRAVERSAL ✨
  // Developer assumes gateway always returns transaction.refundId
  // Crashes: TypeError: Cannot read properties of null (reading 'refundId')
  const refundId = gatewayResponse.transaction?.refundId;

  res.json({
    orderId: order.id,
    refundId: refundId,
    message: "Refund processed",
  });
});

export default router;
