import { getUserById } from "./userService";
import { renderTemplate } from "./templateService";

export function sendBlast(userIds: string[], template: string): number {
    let sentCount = 0;
    
    for (const id of userIds) {
        const user = getUserById(id);
        if (user) {
            // Passes the user into the template engine unaware of null profiles
            const body = renderTemplate(template, user);
            console.log(`Sending to ${user.email}: ${body}`);
            sentCount++;
        }
    }
    
    return sentCount;
}
