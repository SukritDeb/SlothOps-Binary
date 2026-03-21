import request from "supertest";
import { app } from "../src/index";

describe("Sync Route", () => {
  it("should accept a sync job (ignoring background processing)", async () => {
    const response = await request(app).get("/sync/batch");
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty("message", "Sync job accepted");
    expect(response.body).toHaveProperty("expectedCount", 3);
  });
});
