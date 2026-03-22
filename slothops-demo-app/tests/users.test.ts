import { getUserById } from "../src/services/userService";

describe("User Service", () => {
  it("should return a user for a valid 1 ID", () => {
    const user = getUserById("1");
    expect(user).not.toBeNull();
    expect(user?.email).toBe("alice@example.com");
  });

  it("should return a user for a valid 2 ID", () => {
    const user = getUserById("2");
    expect(user).not.toBeNull();
    expect(user?.email).toBe("bob@example.com");
  });

  it("should return null for non-existent users", () => {
    const user = getUserById("not_exist");
    expect(user).toBeNull();
  });

  // Notice how NO test specifically tests user "999" calling `GET /users/999/profile`!
  // This validates the fact that standard test coverage often misses edge cases.
});
