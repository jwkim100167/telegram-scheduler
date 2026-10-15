import axios from "axios";
import * as cheerio from "cheerio";
import { createClient } from "@supabase/supabase-js";
import { ScheduleJob } from "../types";
import { logger } from "../../logger";
import { config } from "../../config";

const TEAM_NAME_TO_ID: Record<string, number> = {
  KIA: 1, KIA타이거즈: 1,
  삼성: 2, 삼성라이온즈: 2,
  LG: 3, LG트윈스: 3,
  두산: 4, 두산베어스: 4,
  KT: 5, KT위즈: 5,
  한화: 6, 한화이글스: 6,
  롯데: 7, 롯데자이언츠: 7,
  SSG: 8, SSG랜더스: 8,
  NC: 9, NC다이노스: 9,
  키움: 10, 키움히어로즈: 10,
};

function toTeamId(name: string): number | null {
  if (!name) return null;
  if (TEAM_NAME_TO_ID[name]) return TEAM_NAME_TO_ID[name];
  for (const [key, val] of Object.entries(TEAM_NAME_TO_ID)) {
    if (name.includes(key) || key.includes(name)) return val;
  }
  return null;
}

function getKstDate(): Date {
  return new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
}

function toYyyymmdd(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("");
}

const KBO_CALENDAR_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetMonthSchedule";

type CalendarCell = { Text: string };
type CalendarRow  = { row: CalendarCell[] };

// KBO 공식 ASMX - form-urlencoded POST로 월별 캘린더 조회 (인증 불필요)
async function fetchKboCalendar(year: number, month: number): Promise<CalendarRow[]> {
  const gameMonth = String(month).padStart(2, "0");
  const res = await axios.post(
    KBO_CALENDAR_URL,
    `leId=1&srIdList=0%2C9%2C6&seasonId=${year}&gameMonth=${gameMonth}&teamId=0`,
    {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
      },
      // text/plain로 응답하므로 JSON 자동 파싱 안 됨 → 수동 파싱
      transformResponse: [(data: string) => data],
      timeout: 10000,
    }
  );

  const json = JSON.parse(res.data as string);
  return (json.rows ?? []) as CalendarRow[];
}

// 캘린더 row 배열에서 오늘 이후 예정 경기만 추출
// 예정경기 형식: <li>원정팀 : 홈팀 [경기장]</li>
// 완료경기 형식: <a href='...'><li>팀A <b>점수 : 점수</b> 팀B <img...></li></a>
function parseScheduledGames(
  rows: CalendarRow[],
  year: string,
  month: string,
  todayStr: string
): Record<string, Array<[number, number]>> {
  const byDate: Record<string, Array<[number, number]>> = {};
  // <li>AWAY : HOME [경기장]</li> — <b> 등 inner 태그 없는 것만 매칭하여 예정경기만 잡음
  const gameRe = /<li>([^<>]+?)\s*:\s*([^<>\[\]]+?)\s*\[[^\]]+\]<\/li>/g;
  const dayRe  = /class="dayNum">(\d+)/;

  for (const weekRow of rows) {
    for (const cell of weekRow.row ?? []) {
      const text = cell.Text ?? "";
      const dayMatch = text.match(dayRe);
      if (!dayMatch) continue;

      const day = dayMatch[1].padStart(2, "0");
      const dateStr = `${year}${month}${day}`;
      if (dateStr < todayStr) continue;

      gameRe.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = gameRe.exec(text)) !== null) {
        const awayName = m[1].trim();
        const homeName = m[2].trim();
        const awayId = toTeamId(awayName);
        const homeId = toTeamId(homeName);

        if (!awayId || !homeId) {
          logger.warn(`[kbo-schedule] Unknown team: away="${awayName}" home="${homeName}"`);
          continue;
        }

        if (!byDate[dateStr]) byDate[dateStr] = [];
        byDate[dateStr].push([homeId, awayId]);
      }
    }
  }

  return byDate;
}

// 오늘 또는 가장 가까운 미래 경기 날짜 3개 반환
async function fetchNearestGameDates(): Promise<{ date: string; games: Array<[number, number]> }[]> {
  const today = getKstDate();
  const todayStr = toYyyymmdd(today);

  // 이번 달 + 다음 달 조회 (월 경계 처리)
  const monthsToFetch = [
    { year: today.getFullYear(), month: today.getMonth() + 1 },
    {
      year: today.getMonth() === 11 ? today.getFullYear() + 1 : today.getFullYear(),
      month: today.getMonth() === 11 ? 1 : today.getMonth() + 2,
    },
  ];

  const byDate: Record<string, Array<[number, number]>> = {};

  for (const { year, month } of monthsToFetch) {
    let rows: CalendarRow[];
    try {
      rows = await fetchKboCalendar(year, month);
    } catch (e) {
      logger.error(`[kbo-schedule] Failed to fetch ${year}-${month}`, e);
      continue;
    }

    logger.info(`[kbo-schedule] ${year}-${String(month).padStart(2, "0")}: ${rows.length} calendar rows`);

    const yearStr  = String(year);
    const monthStr = String(month).padStart(2, "0");
    const parsed = parseScheduledGames(rows, yearStr, monthStr, todayStr);
    Object.assign(byDate, parsed);

    if (Object.keys(byDate).length >= 3) break;
  }

  const sortedDates = Object.keys(byDate).sort().slice(0, 3);
  if (sortedDates.length === 0) {
    logger.warn("[kbo-schedule] No upcoming games found");
    return [];
  }

  return sortedDates.map((d) => ({
    date: `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`,
    games: byDate[d],
  }));
}

type H2HRow = { season: number; team_id: number; opp_id: number; wins: number; draws: number; losses: number; updated_at: string };

const TEAM_NAME_TO_ID_H2H: Record<string, number> = {
  KIA: 1, 삼성: 2, LG: 3, 두산: 4, KT: 5,
  한화: 6, 롯데: 7, SSG: 8, NC: 9, 키움: 10,
};

function toTeamIdH2H(name: string): number | null {
  const trimmed = name.trim();
  if (TEAM_NAME_TO_ID_H2H[trimmed]) return TEAM_NAME_TO_ID_H2H[trimmed];
  for (const [key, val] of Object.entries(TEAM_NAME_TO_ID_H2H)) {
    if (trimmed.includes(key) || key.includes(trimmed)) return val;
  }
  return null;
}

// koreabaseball.com에서 H2H 스크래핑 후 DB 업데이트
async function scrapeAndSaveH2H(supabase: ReturnType<typeof createClient>): Promise<void> {
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
  const season = getKstDate().getFullYear();
  const now = new Date().toISOString();
  const rows: H2HRow[] = [];

  const h2hTable = $("table").filter((_, el) => {
    const cells = $(el).find("tr").first().find("th, td");
    return cells.eq(0).text().trim() === "팀명" && cells.eq(1).text().includes("승-패-무");
  }).first();

  if (!h2hTable.length) {
    logger.warn("[kbo-schedule] H2H 테이블 파싱 실패 — 스킵");
    return;
  }

  const tableRows = h2hTable.find("tr").toArray();
  const colTeamIds: Array<number | null> = [];
  $(tableRows[0]).find("th, td").each((i, cell) => {
    if (i === 0) return;
    colTeamIds.push(toTeamIdH2H($(cell).text().trim().replace(/\(.*\)/, "").trim()));
  });

  for (let r = 1; r < tableRows.length; r++) {
    const cells = $(tableRows[r]).find("th, td").toArray();
    if (cells.length < 2) continue;
    const rowTeamId = toTeamIdH2H($(cells[0]).text().trim());
    if (!rowTeamId) continue;

    for (let c = 1; c < cells.length; c++) {
      const colTeamId = colTeamIds[c - 1];
      if (!colTeamId || colTeamId === rowTeamId) continue;
      const cellText = $(cells[c]).text().trim();
      if (cellText === "■" || cellText === "") continue;
      const parts = cellText.split("-").map((s) => parseInt(s.trim(), 10));
      if (parts.length < 2 || parts.some(isNaN)) continue;
      rows.push({ season, team_id: rowTeamId, opp_id: colTeamId, wins: parts[0] ?? 0, losses: parts[1] ?? 0, draws: parts[2] ?? 0, updated_at: now });
    }
  }

  if (rows.length === 0) {
    logger.warn("[kbo-schedule] H2H 파싱 데이터 없음 — 스킵");
    return;
  }

  const { error } = await (supabase as any).from("kboH2H").upsert(rows, { onConflict: "season,team_id,opp_id" });
  if (error) {
    logger.error("[kbo-schedule] H2H DB 저장 실패", error);
  } else {
    logger.info(`[kbo-schedule] H2H 스크래핑 완료 — ${rows.length}건 저장`);
  }
}

// kboH2H 테이블에서 상대전적 맵 구성
async function buildH2HMap(
  supabase: ReturnType<typeof createClient>,
  season: number
): Promise<Map<string, string | null>> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data, error } = await (supabase as any)
    .from("kboH2H")
    .select("team_id, opp_id, wins, draws, losses")
    .eq("season", season);

  if (error || !data) {
    logger.warn("[kbo-schedule] H2H 조회 실패", error);
    return new Map();
  }

  const map = new Map<string, string | null>();
  for (const r of (data as H2HRow[])) {
    const total = r.wins + r.draws + r.losses;
    if (total === 0) continue;
    const val = r.draws > 0 ? `${r.wins}:${r.losses}:${r.draws}` : `${r.wins}:${r.losses}`;
    map.set(`${r.team_id}-${r.opp_id}`, val);
  }
  return map;
}

export const kboScheduleJob: ScheduleJob = {
  name: "kbo-schedule",
  cronExpression: "0 5 * * *", // 매일 05:00 KST
  timezone: "Asia/Seoul",
  enabled: true,
  execute: async () => {
    const supabase = createClient(config.kboSupabase.url, config.kboSupabase.serviceKey);

    // 1. H2H 스크래핑 & DB 업데이트
    try {
      await scrapeAndSaveH2H(supabase as ReturnType<typeof createClient>);
    } catch (e) {
      logger.error("[kbo-schedule] H2H 스크래핑 실패 — 기존 데이터로 진행", e);
    }

    // 2. 경기 일정 조회
    const results = await fetchNearestGameDates();
    if (results.length === 0) {
      logger.warn("[kbo-schedule] No games to save, skipping");
      return;
    }

    // 3. 일정 저장
    for (const { date, games } of results) {
      logger.info(`[kbo-schedule] Saving ${date}: ${games.length} games`);
      const { error } = await supabase
        .from("kboTodaySchedule")
        .upsert(
          { date, games, updated_at: new Date().toISOString() },
          { onConflict: "date" }
        );

      if (error) {
        logger.error(`[kbo-schedule] Failed to save ${date}`, error);
        throw error;
      }
    }

    // H2H 상대전적 패치
    const season = getKstDate().getFullYear();
    const h2hMap = await buildH2HMap(supabase as ReturnType<typeof createClient>, season);

    if (h2hMap.size === 0) {
      logger.warn("[kbo-schedule] H2H 데이터 없음 — 상대전적 패치 스킵");
    } else {
      for (const { date, games } of results) {
        const patched = games.map(([homeId, awayId]) => {
          const h2h = h2hMap.get(`${homeId}-${awayId}`) ?? null;
          return [homeId, awayId, h2h];
        });

        const { error } = await supabase
          .from("kboTodaySchedule")
          .update({ games: patched, updated_at: new Date().toISOString() })
          .eq("date", date);

        if (error) {
          logger.error(`[kbo-schedule] H2H 패치 실패 ${date}`, error);
        } else {
          logger.info(`[kbo-schedule] H2H 패치 완료 ${date}`);
        }
      }
    }

    logger.info("[kbo-schedule] Done");
  },
};
