import { createClient } from "@supabase/supabase-js";
import { ScheduleJob } from "../types";
import { sendMessage } from "../../sender/messageSender";
import { config } from "../../config";
import { logger } from "../../logger";

interface SectorStat {
  sector_id: string;
  mention_count: number;
  sectors: { sector_name: string } | { sector_name: string }[] | null;
}

interface EnrichedStat {
  sectorId: string;
  name: string;
  thisWeek: number;
  lastWeek: number;
  delta: number;
  rate: number; // %
}

// 임시 섹터 → 대표 ETF 매핑 (추후 DB/프로세스로 교체)
const SECTOR_ETF: Record<string, string> = {
  "반도체":     "KODEX 반도체",
  "2차전지":    "KODEX 2차전지산업",
  "바이오":     "KODEX 바이오",
  "IT":         "KODEX IT",
  "소프트웨어": "KODEX 소프트웨어",
  "자동차":     "KODEX 자동차",
  "금융":       "KODEX 은행",
  "에너지":     "KODEX 에너지화학",
  "철강":       "KODEX 철강",
  "건설":       "KODEX 건설",
  "유통":       "KODEX 유통",
  "음식료":     "KODEX 음식료&농업",
  "화학":       "KODEX 에너지화학",
  "헬스케어":   "KODEX 헬스케어",
  "게임":       "KODEX 게임산업",
  "미디어":     "KODEX 미디어&엔터테인먼트",
  "통신":       "KODEX 통신",
  "조선":       "KODEX 조선",
  "항공":       "TIGER 항공사",
  "증권":       "KODEX 증권",
  "보험":       "KODEX 보험",
  "기계":       "KODEX 기계장비",
  "유틸리티":   "TIGER 유틸리티",
  "부동산":     "TIGER 부동산리츠부동산인프라",
};

function getWeekStart(offsetWeeks = 0): string {
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
  const day = now.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(now);
  monday.setDate(now.getDate() + diff + offsetWeeks * 7);
  return monday.toISOString().slice(0, 10);
}

function getSectorName(stat: SectorStat): string {
  const s = stat.sectors;
  return (Array.isArray(s) ? s[0]?.sector_name : s?.sector_name) ?? stat.sector_id;
}

function isEtc(name: string): boolean {
  return name.includes("기타") || name.toLowerCase() === "etc";
}

function top3Lines(
  items: EnrichedStat[],
  key: keyof Pick<EnrichedStat, "thisWeek" | "delta" | "rate">,
  formatter: (v: number) => string
): string[] {
  const sorted = [...items].sort((a, b) => b[key] - a[key]).slice(0, 3);
  if (sorted.length === 0) return ["  데이터 없음"];
  return sorted.map((s, i) => `  ${i + 1}위  <b>${s.name}</b>  ${formatter(s[key])}`);
}

function buildMessage(enriched: EnrichedStat[], weekStart: string): string {
  const top1 = [...enriched].sort((a, b) => b.thisWeek - a.thisWeek)[0];
  const etfName = top1 ? (SECTOR_ETF[top1.name] ?? "—") : "—";

  const lines: string[] = [
    `<b>📊 주간 섹터 리포트</b>  (${weekStart} 기준)`,
    ``,
    `<b>🔢 언급량 TOP 3</b>`,
    ...top3Lines(enriched, "thisWeek", (v) => `${v.toLocaleString()}건`),
    ``,
    `<b>📈 언급증가량 TOP 3</b>`,
    ...top3Lines(enriched, "delta", (v) => `+${v.toLocaleString()}건`),
    ``,
    `<b>🚀 언급증가율 TOP 3</b>`,
    ...top3Lines(enriched, "rate", (v) => `+${v.toFixed(1)}%`),
    ``,
    `<b>🏆 이번 주 관심 ETF</b>  <i>(임시)</i>`,
    `  ${top1?.name ?? "—"} 1위 → <b>${etfName}</b>`,
  ];

  return lines.join("\n");
}

export const weeklyHeatReportJob: ScheduleJob = {
  name: "weekly-heat-report",
  cronExpression: "55 21 * * 6", // 매주 토요일 21:55 KST
  timezone: "Asia/Seoul",
  enabled: true,
  execute: async () => {
    const supabase = createClient(
      config.supabase.url,
      config.supabase.serviceKey
    );

    const thisWeekStart = getWeekStart(0);
    const lastWeekStart = getWeekStart(-1);

    const [thisRes, lastRes] = await Promise.all([
      supabase
        .from("weekly_sector_stats")
        .select("sector_id, mention_count, sectors(sector_name)")
        .eq("week_start", thisWeekStart),
      supabase
        .from("weekly_sector_stats")
        .select("sector_id, mention_count, sectors(sector_name)")
        .eq("week_start", lastWeekStart),
    ]);

    if (thisRes.error) {
      logger.error("이번 주 weekly_sector_stats 조회 실패", thisRes.error);
      throw thisRes.error;
    }

    const thisWeekMap = new Map<string, SectorStat>(
      ((thisRes.data ?? []) as SectorStat[]).map((s) => [s.sector_id, s])
    );
    const lastWeekMap = new Map<string, SectorStat>(
      ((lastRes.data ?? []) as SectorStat[]).map((s) => [s.sector_id, s])
    );

    const enriched: EnrichedStat[] = [];
    for (const [sectorId, stat] of thisWeekMap) {
      const name = getSectorName(stat);
      if (isEtc(name)) continue;

      const thisWeek = stat.mention_count ?? 0;
      const lastWeek = lastWeekMap.get(sectorId)?.mention_count ?? 0;
      const delta = thisWeek - lastWeek;
      const rate = lastWeek > 0 ? (delta / lastWeek) * 100 : 0;

      enriched.push({ sectorId, name, thisWeek, lastWeek, delta, rate });
    }

    if (enriched.length === 0) {
      logger.warn(
        `[weekly-heat-report] weekly_sector_stats 조회 결과 없음 (week_start=${thisWeekStart}). ` +
        `thisWeekRaw=${thisRes.data?.length ?? 0}건, lastWeekRaw=${lastRes.data?.length ?? 0}건`
      );
    }

    const message = buildMessage(enriched, thisWeekStart);
    logger.info(`[weekly-heat-report] 전송:\n${message}`);
    await sendMessage(config.telegram.targetChatId, message, {
      parseMode: "HTML",
    });
  },
};
