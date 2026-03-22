import { aggregateByCategory } from '../../src/services/aggregatorService';
import { TransactionCategory } from '../../src/services/dataService';

describe('aggregateByCategory', () => {
  it('should correctly aggregate transaction categories', () => {
    const categories: TransactionCategory[] = [
      {
        name: 'sales',
        items: [{ id: '1', amount: 100 }, { id: '2', amount: 50 }],
        metadata: { currency: 'USD', region: 'US' },
      },
      {
        name: 'subscriptions',
        items: [{ id: '3', amount: 20 }],
        metadata: { currency: 'EUR', region: 'EU' },
      },
    ];

    const result = aggregateByCategory(categories);

    expect(result).toEqual([
      { category: 'sales', total: 150, count: 2, currency: 'USD' },
      { category: 'subscriptions', total: 20, count: 1, currency: 'EUR' },
    ]);
  });

  it('should correctly handle refunds with metadata, which previously caused a crash', () => {
    const categories: TransactionCategory[] = [
      {
        name: 'refunds',
        items: [{ id: '4', amount: -25 }],
        metadata: { currency: 'USD', region: 'US' },
      },
    ];

    const result = aggregateByCategory(categories);

    expect(result).toEqual([
      { category: 'refunds', total: -25, count: 1, currency: 'USD' },
    ]);
  });

  it('should return an empty array if given an empty array', () => {
    const categories: TransactionCategory[] = [];
    const result = aggregateByCategory(categories);
    expect(result).toEqual([]);
  });

  it('should handle categories with no items', () => {
    const categories: TransactionCategory[] = [
      {
        name: 'empty_category',
        items: [],
        metadata: { currency: 'JPY', region: 'JP' },
      },
    ];

    const result = aggregateByCategory(categories);

    expect(result).toEqual([
      { category: 'empty_category', total: 0, count: 0, currency: 'JPY' },
    ]);
  });

  it('should correctly round totals to two decimal places', () => {
    const categories: TransactionCategory[] = [
        {
            name: 'sales',
            items: [{ id: '1', amount: 10.123 }, { id: '2', amount: 5.456 }],
            metadata: { currency: 'USD', region: 'US' },
        }
    ];

    const result = aggregateByCategory(categories);
    expect(result[0].total).toBe(15.58);
  });
});
