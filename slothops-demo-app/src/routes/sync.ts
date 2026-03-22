import { Router } from "express";

export const syncRouter = Router();

// Mock database interactions
const fetchInventory = async (id: string) => {
    return new Promise(resolve => setTimeout(() => resolve({ id, qty: 10 }), 100));
}

syncRouter.get("/batch", async (req, res, next) => {
    try {
        const productIds = ["p_1", "p_2", "p_3"];
        let syncedCount = 0;

        // ✨ BUG 4 ✨
        // Floating Promise / Async Loop Bug
        // developers often use async inside a regular .forEach() expecting it to block.
        // It does NOT block. The route completes, and if one of these fails LATER,
        // it results in an unhandled rejection that crashes the Node process or causes silent data loss.
        
        productIds.forEach(async (id) => {
            const data = await fetchInventory(id);
            if (id === "p_3") {
                // We force an error asynchronously!
                // Because it's not wrapped in Promise.all and awaited, 
                // this promise rejects into the void. Sentry WILL catch it globally.
                throw new Error(`Inventory sync failed for ${id}: Connection dropped`);
            }
            syncedCount++;
        });

        // This sends immediately, before the promises finish!
        res.json({ message: "Sync job accepted", expectedCount: productIds.length });
    } catch (e) {
        // This catch block will NEVER catch the forEach error.
        next(e);
    }
});
