import { execFile } from "child_process";
import { ScheduleJob } from "../types";
import { logger } from "../../logger";
import path from "path";

const PYTHON = "D:\\miniconda\\python.exe";
const CWD = path.resolve(__dirname, "../../../../");

function runPython(args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, args, { cwd: CWD }, (error, stdout, stderr) => {
      if (stdout) logger.info(stdout.trim());
      if (stderr) logger.warn(stderr.trim());
      if (error) reject(error);
      else resolve();
    });
  });
}

export const burnCollectAndAggregateJob: ScheduleJob = {
  name: "burn-collect-aggregate",
  cronExpression: "0 21 * * 6", // 매주 토요일 21:00 KST
  timezone: "Asia/Seoul",
  enabled: true,
  execute: async () => {
    await runPython(["-m", "collector.main", "seed-krx"]);
    await runPython(["-m", "collector.main", "collect"]);
    await runPython(["-m", "collector.main", "collect-us"]);
    // collect 완전 완료 후 집계 — 두 잡을 분리하면 race condition 발생
    await runPython(["-m", "collector.main", "aggregate"]);
    logger.info("collect + aggregate 완료");
  },
};
