import "dotenv/config";
import { kboScheduleJob } from "../src/scheduler/jobs/kboSchedule";

(async () => {
  console.log("[runKboSchedule] Starting...");
  await kboScheduleJob.execute();
  console.log("[runKboSchedule] Done");
  process.exit(0);
})().catch((e) => {
  console.error("[runKboSchedule] Error:", e);
  process.exit(1);
});
