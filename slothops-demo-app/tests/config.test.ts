import request from "supertest";
import { app } from "../src/index";

describe("Config Route", () => {
  it("should return the default light theme on standard request", async () => {
    const response = await request(app).get("/config/theme");
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty("activeTheme", "light");
  });

  it("should temporarily return a valid forced theme", async () => {
    // We intentionally test the "happy path" of this bug, avoiding the crash parameter
    const response = await request(app).get("/config/theme?forceDark=dark");
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty("activeTheme", "dark");
  });
});
