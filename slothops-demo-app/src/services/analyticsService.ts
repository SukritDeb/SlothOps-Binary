/**
 * Analytics Service — orchestrates daily report generation.
 *
 * Calls dataService to fetch raw data, then aggregatorService
 * to produce category summaries.
 */

import { fetchTransactionData } from "./dataService";
import { aggregateByCategory, CategorySummary } from "./aggregatorService";

export interface DailyReport {
  date: string;
  categories: CategorySummary[];
  grandTotal: number;
}

export function generateDailyReport(): DailyReport {
  const rawData = fetchTransactionData();
  const summaries = aggregateByCategory(rawData);  // ← crashes inside here

  const grandTotal = summaries.reduce((sum, s) => sum + s.total, 0);

  return {
    date: new Date().toISOString().split("T")[0],
    categories: summaries,
    grandTotal: parseFloat(grandTotal.toFixed(2)),
  };
}
