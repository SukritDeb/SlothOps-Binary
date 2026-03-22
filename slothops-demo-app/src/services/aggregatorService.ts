/**
 * Aggregator Service — groups transaction data by category
 * and formats a summary for reporting.
 *
 * CRASH SITE of Bug #11:
 *   `category.metadata.currency` throws TypeError when
 *   metadata is null (the "refunds" category from dataService).
 */

import { TransactionCategory } from "./dataService";

export interface CategorySummary {
  category: string;
  total: number;
  count: number;
  currency: string;
}

export function aggregateByCategory(
  categories: TransactionCategory[]
): CategorySummary[] {
  return categories.map((category) => {
    const total = category.items.reduce((sum, item) => sum + item.amount, 0);

    // FIX: The type for TransactionCategory now guarantees metadata is not null,
    // so the unsafe non-null assertion is no longer needed.
    const currency = category.metadata.currency;

    return {
      category: category.name,
      total: parseFloat(total.toFixed(2)),
      count: category.items.length,
      currency,
    };
  });
}
