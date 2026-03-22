/**
 * Data Service — provides raw transaction data for analytics.
 *
 * ROOT CAUSE of Bug #11:
 *   The "refunds" category has `metadata: null` instead of
 *   a proper { currency, region } object.  Every other category
 *   has valid metadata, so this only crashes when the daily
 *   report includes refund data.
 */

export interface TransactionCategory {
  name: string;
  items: { id: string; amount: number }[];
  metadata: { currency: string; region: string };
}

const mockTransactionData: TransactionCategory[] = [
  {
    name: "sales",
    items: [
      { id: "txn-001", amount: 49.99 },
      { id: "txn-002", amount: 129.50 },
      { id: "txn-003", amount: 9.99 },
    ],
    metadata: { currency: "USD", region: "US" },
  },
  {
    name: "subscriptions",
    items: [
      { id: "txn-010", amount: 14.99 },
      { id: "txn-011", amount: 14.99 },
    ],
    metadata: { currency: "USD", region: "EU" },
  },
  {
    name: "refunds",
    items: [
      { id: "txn-020", amount: -29.99 },
      { id: "txn-021", amount: -5.00 },
    ],
    metadata: { currency: "USD", region: "US" },   // ← FIX: added missing metadata
  },
];

export function fetchTransactionData(): TransactionCategory[] {
  return mockTransactionData;
}
