import { Router } from "express";
import { calculateShippingForCart } from "../services/shippingService";

export const shippingRouter = Router();

shippingRouter.post("/calculate/:cartId", (req, res) => {
  const { cartId } = req.params;
  
  // This will trigger the Bug #9 deep call chain (4 files deep)
  // routes/shipping.ts -> shippingService.ts -> pricingService.ts -> inventoryService.ts
  const shippingCost = calculateShippingForCart(cartId);
  
  res.json({
    cartId,
    shippingCost,
    currency: "USD"
  });
});

export default shippingRouter;
