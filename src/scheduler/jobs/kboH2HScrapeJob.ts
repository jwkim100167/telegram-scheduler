import axios from "axios";
import * as cheerio from "cheerio";
import { createClient } from "@supabase/supabase-js";
import { ScheduleJob } from "../types";
import { logger } from "../../logger";
import { config } from "../../config";

const TEAM_NAME_TO_ID: Record<string, number> = {
  KIA: 1, 삼성: 2, LG: 3, 두산: 4, KT: 5,
  한화: 6, 롯데: 7, SSG: 8, NC: 9, 키움: 10,
};

function toTeamId(name: string): number | null {
  const trimmed = name.trim();
  if (TEAM_NAME_TO_ID[trimmed]) return TEAM_NAME_TO_ID[trimmed];
  for (const [key, val] of Object.entries(TEAM_NAME_TO_ID)) {
    if (trimmed.includes(key) || key.includes(trimmed)) return val;
  }
  return null;
}

type H2HRecord = {
  season: number; team_id: number; opp_id: number;
  wins: number; draws: number; losses: number; updated_at: string;
};

async function scrapeH2H(): Promise<H2HRecord[]> {
  const res = await axios.get(
    "https://www.koreabaseball.com/record/teamrank/teamrank.aspx",
    {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        Referer: "https://www.koreabaseball.com/",
      },
      timeout: 15000,
    }
  );

  const $ = cheerio.load(res.data as string);
  const season = new Date().getFullYear();
  const now = new Date().toISOString();
  const rows: H2HRecord[] = [];

  const h2hTable = $("table").filter((_, el) => {
    const firstRow = $(el).find("tr").first();
    const cells = firstRow.find("th, td");
    return (
      cells.eq(0).text().trim() === "팀명" &&
      cells.eq(1).text().includes("승-패-무")
    );
  }).first();

  if (!h2hTable.length) {
    throw new Error("[kbo-h2h-scrape] 팀간 승패표 테이블을 찾지 못했습니다");
  }

  const tableRows = h2hTable.find("tr").toArray();

  const colTeamIds: Array<number | null> = [];
  $(tableRows[0]).find("th, td").each((i, cell) => {
    if (i === 0) return;
    const text = $(cell).text().trim().replace(/\(.*\)/, "").trim();
    colTeamIds.push(toTeamId(text));
  });

  for (let r = 1; r < tableRows.length; r++) {
    const cells = $(tableRows[r]).find("th, td").toArray();
    if (cells.length < 2) continue;

    const rowTeamId = toTeamId($(cells[0]).text().trim());
    if (!rowTeamId) continue;

    for (let c = 1; c < cells.length; c++) {
      const colTeamId = colTeamIds[c - 1];
      if (!colTeamId || colTeamId === rowTeamId) continue;

      const cellText = $(cells[c]).text().trim();
      if (cellText === "■" || cellText === "") continue;

      const parts = cellText.split("-").map((s) => parseInt(s.trim(), 10));
      if (parts.length < 2 || parts.some(isNaN)) continue;

      rows.push({
        season,
        team_id: rowTeamId,
        opp_id: colTeamId,
        wins:   parts[0] ?? 0,
        losses: parts[1] ?? 0,
        draws:  parts[2] ?? 0,
        updated_at: now,
      });
    }
  }

  return rows;
}

export const kboH2HScrapeJob: ScheduleJob = {
  name: "kbo-h2h-scrape",
  cronExpression: "30 0 * * *", // 매일 00:30 KST (경기 종료 후)
  timezone: "Asia/Seoul",
  enabled: true,
  execute: async () => {
    const rows = await scrapeH2H();
    logger.info(`[kbo-h2h-scrape] 파싱 완료: ${rows.length}건`);

    if (rows.length === 0) {
      logger.warn("[kbo-h2h-scrape] 파싱된 데이터 없음 — 업데이트 스킵");
      return;
    }

    const supabase = createClient(config.kboSupabase.url, config.kboSupabase.serviceKey);
    const { error } = await (supabase as any)
      .from("kboH2H")
      .upsert(rows, { onConflict: "season,team_id,opp_id" });

    if (error) {
      logger.error("[kbo-h2h-scrape] DB 저장 실패", error);
      throw error;
    }

    logger.info(`[kbo-h2h-scrape] Done — ${rows.length}건 저장`);
  },
};
