import { weeklyHeatReportJob } from "./scheduler/jobs/weeklyHeatReport";
import { logger } from "./logger";

(async () => {
  logger.info("주간 리포트 테스트 발송...");
  await weeklyHeatReportJob.execute();
  logger.info("완료");
  process.exit(0);
})();
