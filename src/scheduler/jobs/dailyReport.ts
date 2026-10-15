import fs from "fs";
import path from "path";
import { ScheduleJob } from "../types";
import { logger } from "../../logger";
import { config } from "../../config";
import { sendMessage } from "../../sender/messageSender";

const LOG_PATH = path.join("logs", "combined.log");

const JOB_DISPLAY: Record<string, string> = {
  "morning-weather":   "아침 날씨",
  "weekly-heat-report": "주간 소각 리포트",
  "burn-collect":      "소각 수집",
  "burn-aggregate":    "소각 집계",
  "kbo-schedule":      "KBO 일정 + H2H",
};

interface JobResult {
  name: string;
  success: boolean;
  errorMsg?: string;
}

function getYesterdayPrefix(): string {
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
  d.setDate(d.getDate() - 1);
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}

function parseYesterdayResults(): JobResult[] {
  if (!fs.existsSync(LOG_PATH)) return [];

  const prefix = getYesterdayPrefix();
  const lines = fs.readFileSync(LOG_PATH, "utf-8")
    .split("\n")
    .filter((l) => l.startsWith(prefix));

  // 잡별 started / completed / failed 추적
  const started  = new Set<string>();
  const completed = new Set<string>();
  const failed   = new Map<string, string>();

  const runRe   = /Running job \[(.+?)\]/;
  const doneRe  = /Job \[(.+?)\] completed/;
  const failRe  = /Job \[(.+?)\] failed/;
  const errRe   = /\[error\]:.+/;

  let lastError = "";
  for (const line of lines) {
    const errMatch = line.match(errRe);
    if (errMatch) lastError = errMatch[0].replace(/\[error\]:\s*/, "").trim();

    const run = line.match(runRe);
    if (run) { started.add(run[1]); lastError = ""; }

    const done = line.match(doneRe);
    if (done) completed.add(done[1]);

    const fail = line.match(failRe);
    if (fail) failed.set(fail[1], lastError);
  }

  const results: JobResult[] = [];
  for (const name of started) {
    if (completed.has(name)) {
      results.push({ name, success: true });
    } else {
      results.push({ name, success: false, errorMsg: failed.get(name) });
    }
  }

  return results;
}

function buildMessage(results: JobResult[]): string {
  const prefix = getYesterdayPrefix();
  const lines: string[] = [`[스케줄러 일일 리포트] ${prefix}\n`];

  if (results.length === 0) {
    lines.push("어제 실행된 잡이 없습니다.");
    return lines.join("\n");
  }

  for (const r of results) {
    const display = JOB_DISPLAY[r.name] ?? r.name;
    if (r.success) {
      lines.push(`✅ ${display}`);
    } else {
      lines.push(`❌ ${display}`);
      if (r.errorMsg) lines.push(`   └ ${r.errorMsg.slice(0, 100)}`);
    }
  }

  return lines.join("\n");
}

export const dailyReportJob: ScheduleJob = {
  name: "daily-report",
  cronExpression: "0 9 * * *", // 매일 09:00 KST
  timezone: "Asia/Seoul",
  enabled: true,
  execute: async () => {
    const results = parseYesterdayResults();
    const message = buildMessage(results);
    logger.info(`[daily-report] 전송:\n${message}`);
    await sendMessage(config.telegram.targetChatId, message);
  },
};
