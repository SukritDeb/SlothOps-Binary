import { User } from "./userService";

export function renderTemplate(templateStr: string, user: User): string {
    // BUG: user.profile can be null for incomplete users
    // This crashes with: TypeError: Cannot read properties of null (reading 'displayName')
    return templateStr.replace("{{name}}", user.profile!.displayName);
}
