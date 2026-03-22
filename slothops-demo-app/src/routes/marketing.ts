import { Router } from "express";
import { sendCampaign } from "../services/marketingService";

export const marketingRouter = Router();

marketingRouter.post("/campaigns/:id/send", (req, res) => {
    const { id } = req.params;
    
    // Triggers deep chain: marketing.ts -> marketingService.ts -> emailService.ts -> templateService.ts -> userService.ts
    const sentCount = sendCampaign(id);
    
    res.json({
        campaignId: id,
        status: "sent",
        emailsSent: sentCount
    });
});

export default marketingRouter;
