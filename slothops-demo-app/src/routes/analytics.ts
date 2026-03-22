/**
 * Analytics Routes — daily report generation endpoint.
 * Entry point for Bug #11.
 */

import { Router } from "express";
import { generateDailyReport } from "../services/analyticsService";

const router = Router();

/**
 * GET /analytics/reports/daily
 * Generates a daily analytics report aggregating all transaction categories.
 * Crashes when the refunds category has null metadata.
 */
router.get("/reports/daily", (req, res) => {
  try {
    const report = generateDailyReport();
    res.json(report);
  } catch (err: any) {
    // Let the error propagate to Sentry via the global error handler
    throw err;
  }
});

export default router;
