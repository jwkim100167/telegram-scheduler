import dotenv from "dotenv";

dotenv.config();

function requireEnv(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

export const config = {
  telegram: {
    botToken: requireEnv("TELEGRAM_BOT_TOKEN"),
    targetChatId: requireEnv("TARGET_CHAT_ID"),
  },
  weather: {
    apiKey: process.env.WEATHER_API_KEY ?? "",
    city: process.env.WEATHER_CITY ?? "Seoul",
  },
  supabase: {
    url: requireEnv("SUPABASE_URL"),
    serviceKey: requireEnv("SUPABASE_SERVICE_KEY"),
  },
  kboSupabase: {
    url: requireEnv("KBO_SUPABASE_URL"),
    serviceKey: requireEnv("KBO_SUPABASE_SERVICE_KEY"),
  },
  app: {
    nodeEnv: process.env.NODE_ENV ?? "development",
    logLevel: process.env.LOG_LEVEL ?? "info",
    timezone: process.env.TZ ?? "Asia/Seoul",
  },
};
