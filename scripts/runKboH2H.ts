import "dotenv/config";
import { kboH2HScrapeJob } from "../src/scheduler/jobs/kboH2HScrapeJob";

(async () => {
  console.log("[runKboH2H] Starting...");
  await kboH2HScrapeJob.execute();
  console.log("[runKboH2H] Done");
  process.exit(0);
})().catch((e) => {
  console.error("[runKboH2H] Error:", e);
  process.exit(1);
});
