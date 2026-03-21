import * as Sentry from "@sentry/node";
import { nodeProfilingIntegration } from "@sentry/profiling-node";
import express from "express";
import dotenv from "dotenv";

import usersRouter from "./routes/users";
import ordersRouter from "./routes/orders";
import { syncRouter } from "./routes/sync";
import { configRouter } from "./routes/config";
import path from "path";

dotenv.config();

export const app = express();

// --- 1. Initialize Sentry AS EARLY AS POSSIBLE ---
Sentry.init({
  dsn: process.env.SENTRY_DSN || "",
  integrations: [
    nodeProfilingIntegration(),
  ],
  tracesSampleRate: 1.0,
  profilesSampleRate: 1.0,
});

// --- 2. Sentry Request Handler (must be first middleware) ---
Sentry.setupExpressErrorHandler(app);

app.use(express.json());

// --- 3. Mount Routes ---
app.use(express.static(path.join(__dirname, "public")));
app.use("/users", usersRouter);
app.use("/orders", ordersRouter);
app.use("/sync", syncRouter);
app.use("/config", configRouter);

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

app.get("/debug-sentry", function mainHandler(req, res) {
  throw new Error("My first Sentry error!");
});

// --- 4. Vercel Serverless Freeze Protection ---
// AWS Lambdas freeze the Node.js process the exact microsecond a response is sent.
// We MUST explicitly force Sentry to finish uploading the crash report over the network
// BEFORE we let Express resolve the 500 error, otherwise Sentry never receives the data.
app.use(async (err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error("Caught Unhandled Exception! Flushing to Sentry...");
  Sentry.captureException(err);
  try {
    await Sentry.flush(2000); // 2-second timeout
    console.log("Successfully flushed to Sentry.io!");
  } catch (e) {
    console.error("Sentry flush failed:", e);
  }
  res.status(500).json({ message: "Serverless Crash", error: err.message });
});

const PORT = process.env.PORT || 3000;
if (process.env.NODE_ENV !== "production" && !process.env.VERCEL) {
  app.listen(PORT, () => {
    console.log(`SlothOps Demo App running on port ${PORT}`);
  });
}

export default app;
