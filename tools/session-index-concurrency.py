"""Reproducible local changes to the pinned Apache-2.0 AutoSlides collector.

Applied only to the build copy. Original changed sources are retained in
source/upstream/; the upstream checkout is never modified.
"""
from pathlib import Path

PATCH_ID = "bounded-concurrency-v1"


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError("Pinned collector patch no longer matches: " + before[:90])
    return text.replace(before, after, 1)


def apply(root: Path):
    changes = {}
    for name in ["crawler.ts", "yanhekt.ts", "cli.ts"]:
        path = root / "indexer/src" / name
        original = text = path.read_text(encoding="utf-8")
        if name == "crawler.ts":
            text = replace_once(text, "export interface CrawlerConfig {", "export interface CrawlerConfig {\n  /** Local patch: bounded parallel requests; default preserves serial behavior. */\n  concurrency?: number;")
            text = replace_once(text, "      const id = lane.cursor;\n      const { o, used } = await this.fetchSession(id);\n      steps += used;", """      const ids: number[] = [];
      const width = Math.max(1, Math.min(5, config.concurrency ?? 1));
      for (let k = 0; k < width && steps + k < config.batchSize; k++) {
        const id = lane.cursor + k * spec.dir;
        if (pastEnd(spec, id) || !budget.canAfford(k + 1)) break;
        ids.push(id);
      }
      // Drain ALL in-flight calls before committing, rolling back or backing off.
      // Apply in scan order: a failed id remains the next cursor even when
      // later requests finished sooner. Those later ids are safe to re-fetch.
      const results = await Promise.allSettled(ids.map((id) => this.fetchSession(id)));
      for (let k = 0; k < ids.length; k++) {
      const id = ids[k];
      const result = results[k];
      if (result.status === 'rejected') throw result.reason;
      const { o, used } = result.value;
      steps += used;""")
            text = replace_once(text, "      lane.cursor += spec.dir;\n    }\n    return 'ok';", "      lane.cursor += spec.dir;\n      }\n    }\n    return 'ok';")
            text = replace_once(text, "      for (const id of store.pendingCourses(config.batchSize)) {\n        if (this.stopped() || !budget.canAfford(1)) return used;\n        const c = await this.call(() => this.d.api.course(id));\n        used += 1;", """      const pending = store.pendingCourses(config.batchSize);
      for (let offset = 0; offset < pending.length;) {
        if (this.stopped() || !budget.canAfford(1)) return used;
        const ids: number[] = [];
        const width = Math.max(1, Math.min(5, config.concurrency ?? 1));
        while (ids.length < width && offset < pending.length && budget.canAfford(ids.length + 1)) {
          ids.push(pending[offset++]);
        }
        const results = await Promise.allSettled(ids.map((id) => this.call(() => this.d.api.course(id))));
        for (let k = 0; k < ids.length; k++) {
        const id = ids[k];
        const result = results[k];
        if (result.status === 'rejected') throw result.reason;
        const c = result.value;
        used += 1;""")
            text = replace_once(text, "          this.unexpected('course', id, c);\n        }\n      }", "          this.unexpected('course', id, c);\n        }\n        }\n      }")
        elif name == "yanhekt.ts":
            text = replace_once(text, "  private last = Number.NEGATIVE_INFINITY;", "  private last = Number.NEGATIVE_INFINITY;\n  private queue: Promise<void> = Promise.resolve();")
            text = replace_once(text, "  async wait(): Promise<void> {\n    const jitter", """  wait(): Promise<void> {
    // Reserve start slots serially so concurrent callers cannot share a slot.
    const ready = this.queue.then(() => this.waitTurn());
    this.queue = ready.catch(() => {});
    return ready;
  }

  private async waitTurn(): Promise<void> {
    const jitter""")
        else:
            text = replace_once(text, "  --interval-ms N       time between request starts, min 250 (default 1000 = 1 req/s)", "  --interval-ms N       global request start spacing, min 200 (default 1000)\n  --concurrency N       at most N parallel calls, 1..5 (default 1)")
            text = replace_once(text, "    'interval-ms': { type: 'string', default: '1000' },", "    'interval-ms': { type: 'string', default: '1000' },\n    concurrency: { type: 'string', default: '1' },")
            text = replace_once(text, "num('interval-ms', 250, 600_000)", "num('interval-ms', 200, 600_000)")
            text = replace_once(text, "    const config: CrawlerConfig = {", "    const config: CrawlerConfig = {\n      concurrency: num('concurrency', 1, 5),")
            text = replace_once(text, "${intervalMs} ms between requests`);", "${intervalMs} ms global start spacing, concurrency ${config.concurrency ?? 1}`);")
        banner = "// Locally modified for bounded concurrency, 2026-10-27. See source/local/session-index-concurrency.py.\n"
        if text.startswith("#!/usr/bin/env node\n"):
            text = text.replace("#!/usr/bin/env node\n", "#!/usr/bin/env node\n" + banner, 1)
        else:
            text = banner + text
        path.write_text(text, encoding="utf-8", newline="\n")
        original_path = root / "upstream/indexer/src" / name
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_text(original, encoding="utf-8", newline="\n")
        changes[f"indexer/src/{name}"] = f"upstream/indexer/src/{name}"
    return changes
