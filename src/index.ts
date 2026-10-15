import { config } from "./config";
import { logger } from "./logger";
import { registerJobs } from "./scheduler";

process.env.TZ = config.app.timezone;

logger.info("=== Telegram Scheduler starting ===");
logger.info(`Environment: ${config.app.nodeEnv}`);
logger.info(`Timezone: ${config.app.timezone}`);

registerJobs();

logger.info("All jobs registered. Bot is running...");

// 프로세스 유지 (cron이 백그라운드에서 동작)
process.on("SIGINT", () => {
  logger.info("Received SIGINT — shutting down gracefully");
  process.exit(0);
});

process.on("SIGTERM", () => {
  logger.info("Received SIGTERM — shutting down gracefully");
  process.exit(0);
});

process.on("uncaughtException", (error) => {
  logger.error("Uncaught exception", error);
});

process.on("unhandledRejection", (reason) => {
  logger.error("Unhandled rejection", reason as Error);
});
