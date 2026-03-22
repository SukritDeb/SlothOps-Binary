import { sendBlast } from "./emailService";

export function sendCampaign(campaignId: string): number {
    // Mock fetching campaign data
    // Bug 10 trigger: Campaign "1" explicitly targets user "999", whose profile is null
    const targetUsers = campaignId === "1" ? ["1", "2", "999"] : ["1", "2"];
    const template = "Welcome to SlothStore, {{name}}! Check out our new inventory.";
    
    return sendBlast(targetUsers, template);
}
