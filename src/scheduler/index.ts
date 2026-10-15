import cron from "node-cron";
import { ScheduleJob } from "./types";
import { logger } from "../logger";

// 모든 잡을 여기에 등록
import { morningWeatherJob } from "./jobs/morningWeather";
import { weeklyHeatReportJob } from "./jobs/weeklyHeatReport";
import { burnCollectAndAggregateJob } from "./jobs/burnCollect";
import { kboScheduleJob } from "./jobs/kboSchedule";
import { dailyReportJob } from "./jobs/dailyReport";

const ALL_JOBS: ScheduleJob[] = [
  morningWeatherJob,
  weeklyHeatReportJob,
  burnCollectAndAggregateJob,
  kboScheduleJob,
  dailyReportJob,
  // 새 잡을 추가할 때: 파일 생성 후 여기에 추가
];

export function registerJobs(): void {
  for (const job of ALL_JOBS) {
    if (!job.enabled) {
      logger.info(`Job [${job.name}] is disabled — skipping`);
      continue;
    }

    const valid = cron.validate(job.cronExpression);
    if (!valid) {
      logger.error(`Job [${job.name}] has invalid cron expression: ${job.cronExpression}`);
      continue;
    }

    cron.schedule(
      job.cronExpression,
      async () => {
        logger.info(`Running job [${job.name}]`);
        try {
          await job.execute();
          logger.info(`Job [${job.name}] completed`);
        } catch (error) {
          logger.error(`Job [${job.name}] failed`, error);
        }
      },
      { timezone: job.timezone }
    );

    logger.info(`Job [${job.name}] scheduled — cron: "${job.cronExpression}" (${job.timezone})`);
  }
}
