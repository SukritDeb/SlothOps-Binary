import { getItemDetails } from "./inventoryService";

export function calculateTotalWeight(cartItemIds: string[]): number {
  let totalWeightInKg = 0;

  for (const itemId of cartItemIds) {
    const itemDetails = getItemDetails(itemId);
    
    if (itemDetails && itemDetails.weight) {
      // FIX: Check for the existence of itemDetails.weight before accessing its properties.
      // Digital items or items without a specified weight will be treated as having 0 weight.
      totalWeightInKg += itemDetails.weight.value;
    }
  }

  return totalWeightInKg;
}
