/*
 * JSON fixtures for the code and data components (P1-T16), shaped like the
 * extraction output the consumer pages show (frame V14).
 */

/**
 * A small statement extraction. `fees`, `rewards` and `website` are frame
 * V14's values; `autopay`, `previous_balance` and `transactions` are added so
 * a boolean, a null and an array appear.
 */
export const STATEMENT = {
  fees: 0,
  rewards: {
    reward_dollars: 1087.93,
    rewards_website: "americanexpress.com/cashbackrewards",
    reward_dollars_as_of_date: "08/29/2023",
  },
  website: "americanexpress.com",
  autopay: true,
  previous_balance: null,
  transactions: [
    { date: "08/02", amount: 42.5 },
    { date: "08/05", amount: 13 },
  ],
} as const;

/**
 * A document whose two-space pretty print is exactly `lines` lines long
 * (the spec's performance case is 5,000): an array of 12-line records,
 * padded with scalar items to the exact count.
 */
export function largeJson(lines = 5000): unknown[] {
  // `[` and `]` take two lines; each record takes twelve, each scalar one.
  const body = lines - 2;
  const records = Math.floor(body / 12);
  const out: unknown[] = [];
  for (let i = 0; i < records; i++) {
    out.push({
      id: `txn_${i}`,
      amount: i * 1.25,
      currency: "USD",
      posted: i % 2 === 0,
      memo: null,
      merchant: { name: `Merchant ${i}`, city: "Austin", mcc: 5411 },
    });
  }
  for (let i = 0; i < body - records * 12; i++) {
    out.push(i);
  }
  return out;
}
