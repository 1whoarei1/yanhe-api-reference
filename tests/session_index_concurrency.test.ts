// Local concurrency regressions for the pinned Apache-2.0 AutoSlides collector.
// Built beside its testkit; no live network or media requests.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Crawler, TransientError, rangeLane } from './crawler.ts';
import { SqliteStore } from './store.ts';
import { Budget, Pacer, type Json, type Outcome } from './yanhekt.ts';
import { config, drain, FakeApi, make } from './testkit.ts';

const cfg = { ...config, concurrency: 5, refreshDays: 0, gapThreshold: 1_000_000 };
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const count = (store: SqliteStore) => Number(store.db.prepare('SELECT COUNT(*) AS n FROM sessions').get()!.n);

class SlowApi extends FakeApi {
  active = 0;
  peak = 0;
  coursePeak = 0;
  completed: string[] = [];
  async track<T>(key: string, run: () => Promise<T>): Promise<T> {
    this.active++;
    this.peak = Math.max(this.peak, this.active);
    if (key[0] === 'c') this.coursePeak = Math.max(this.coursePeak, this.active);
    try {
      await delay(Number(key.slice(1)) % 5 === 1 ? 15 : 2);
      return await run();
    } finally {
      this.active--;
      this.completed.push(key);
    }
  }
  session(id: number): Promise<Outcome<Json>> { return this.track(`s${id}`, () => super.session(id)); }
  course(id: number): Promise<Outcome<Json>> { return this.track(`c${id}`, () => super.course(id)); }
}

test('five overlapping session and course requests, saved once despite out-of-order responses', async () => {
  const api = new SlowApi(Array.from({ length: 30 }, (_, i) => i + 1));
  const { crawler, store } = make(api, [rangeLane(1, 30)], undefined, cfg);
  try {
    assert.equal(await drain(crawler), 'idle');
    assert.equal(api.peak, 5);
    assert.equal(api.coursePeak, 5);
    assert.notEqual(api.completed[0], 's1', 'responses really arrive out of order');
    assert.equal(count(store), 30);
    assert.equal(api.calls.filter((c) => c[0] === 's').length, 30);
    assert.equal(crawler.progress()[0].state.cursor, 31);
    assert.equal(api.active, 0);
  } finally { store.close(); }
});

test('a failed concurrent request drains its peers and keeps the cursor before that id', async () => {
  const api = new SlowApi(Array.from({ length: 10 }, (_, i) => i + 1));
  api.failOn.add(3);
  const store = new SqliteStore(':memory:');
  const lane = rangeLane(1, 10);
  try {
    const first = make(api, [lane], store, cfg).crawler;
    await assert.rejects(first.runRound(), TransientError);
    assert.equal(api.active, 0);
    assert.equal(store.loadLane(lane.key)!.cursor, 3);
    assert.equal(count(store), 2);
    api.failOn.clear();
    const resumed = make(api, [lane], store, cfg).crawler;
    assert.equal(await drain(resumed), 'idle');
    assert.equal(count(store), 10);
    assert.equal(resumed.progress()[0].state.cursor, 11);
  } finally { store.close(); }
});

test('parallel retries respect a hard request cap smaller than the next wave', async () => {
  const api = new SlowApi(Array.from({ length: 20 }, (_, i) => i + 1));
  for (let id = 1; id <= 20; id++) api.errorTimes.set(id, 2);
  const store = new SqliteStore(':memory:');
  const budget = new Budget(7, Infinity, 0);
  try {
    const crawler = new Crawler({ api, budget, store, config: { ...cfg, maxUnexpectedInRow: 100 }, lanes: [rangeLane(1, 20)], now: () => 1e6, parkUntil: (t) => t });
    assert.equal(await drain(crawler), 'budget');
    assert.equal(budget.spent, 7);
    assert.equal(api.calls.length, 7);
    assert.equal(api.active, 0);
    assert.ok(api.peak <= 5);
  } finally { store.close(); }
});

test('descending and short final waves never leave the bounded range', async () => {
  const api = new SlowApi([1, 2, 3, 4, 5, 6, 7]);
  const { crawler, store } = make(api, [rangeLane(7, 1)], undefined, cfg);
  try {
    assert.equal(await drain(crawler), 'idle');
    assert.equal(count(store), 7);
    assert.equal(crawler.progress()[0].state.cursor, 0);
    assert.deepEqual(api.calls.filter((c) => c[0] === 's').sort(), ['s1', 's2', 's3', 's4', 's5', 's6', 's7']);
  } finally { store.close(); }
});

test('stop drains the active wave and saves exactly those results for a clean resume', async () => {
  const api = new SlowApi(Array.from({ length: 10 }, (_, i) => i + 1));
  const store = new SqliteStore(':memory:');
  const controller = new AbortController();
  const lane = rangeLane(1, 10);
  const crawler = new Crawler({ api, budget: new Budget(100, Infinity, 0), store, config: cfg, lanes: [lane], signal: controller.signal, now: () => 1e6, parkUntil: (t) => t });
  try {
    const run = crawler.runRound();
    controller.abort();
    assert.equal(await run, 'aborted');
    assert.equal(api.active, 0);
    assert.equal(count(store), 5);
    assert.equal(store.loadLane(lane.key)!.cursor, 6);
    assert.equal(await drain(make(api, [lane], store, cfg).crawler), 'idle');
    assert.equal(count(store), 10);
  } finally { store.close(); }
});

test('a programmer error waits for peers and rolls back the complete wave', async () => {
  const api = new SlowApi([1, 2, 3, 4, 5]);
  const normal = api.session.bind(api);
  api.session = (id) => id === 3 ? Promise.reject(new Error('bad parser')) : normal(id);
  const { crawler, store } = make(api, [rangeLane(1, 5)], undefined, cfg);
  try {
    await assert.rejects(crawler.runRound(), /bad parser/);
    assert.equal(api.active, 0);
    assert.equal(count(store), 0);
    assert.equal(crawler.progress()[0].state.cursor, 1);
  } finally { store.close(); }
});

test('concurrent pacer calls reserve separate global start slots', async () => {
  let clock = 0;
  const starts: number[] = [];
  const pacer = new Pacer(200, () => clock, async (ms) => { clock += ms; });
  await Promise.all(Array.from({ length: 10 }, async () => { await pacer.wait(); starts.push(clock); }));
  assert.equal(starts.length, 10);
  for (let k = 1; k < starts.length; k++) assert.ok(starts[k] - starts[k - 1] >= 200);
});
