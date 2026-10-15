import axios from "axios";
import { ScheduleJob } from "../types";
import { sendMessage } from "../../sender/messageSender";
import { config } from "../../config";
import { logger } from "../../logger";

interface WeatherData {
  temp: number;
  feelsLike: number;
  description: string;
  humidity: number;
  windSpeed: number;
  icon: string;
}

const WEATHER_ICON_MAP: Record<string, string> = {
  "01d": "☀️", "01n": "🌙",
  "02d": "⛅", "02n": "⛅",
  "03d": "☁️", "03n": "☁️",
  "04d": "☁️", "04n": "☁️",
  "09d": "🌧️", "09n": "🌧️",
  "10d": "🌦️", "10n": "🌧️",
  "11d": "⛈️", "11n": "⛈️",
  "13d": "❄️", "13n": "❄️",
  "50d": "🌫️", "50n": "🌫️",
};

async function fetchWeather(): Promise<WeatherData> {
  const url = `https://api.openweathermap.org/data/2.5/weather`;
  const response = await axios.get(url, {
    params: {
      q: config.weather.city,
      appid: config.weather.apiKey,
      units: "metric",
      lang: "kr",
    },
  });

  const data = response.data;
  return {
    temp: Math.round(data.main.temp),
    feelsLike: Math.round(data.main.feels_like),
    description: data.weather[0].description,
    humidity: data.main.humidity,
    windSpeed: data.wind.speed,
    icon: data.weather[0].icon,
  };
}

function buildWeatherMessage(weather: WeatherData): string {
  const now = new Date();
  const dateStr = now.toLocaleDateString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  const icon = WEATHER_ICON_MAP[weather.icon] ?? "🌤️";

  return [
    `${icon} <b>오늘의 날씨 - ${dateStr}</b>`,
    ``,
    `날씨: ${weather.description}`,
    `기온: ${weather.temp}°C (체감 ${weather.feelsLike}°C)`,
    `습도: ${weather.humidity}%`,
    `풍속: ${weather.windSpeed} m/s`,
  ].join("\n");
}

export const morningWeatherJob: ScheduleJob = {
  name: "morning-weather",
  cronExpression: "30 7 * * 1-5", // 월~금 07:30
  timezone: "Asia/Seoul",
  enabled: false,
  execute: async () => {
    if (!config.weather.apiKey) {
      logger.warn("WEATHER_API_KEY not set — sending placeholder message");
      const now = new Date();
      const dateStr = now.toLocaleDateString("ko-KR", {
        timeZone: "Asia/Seoul",
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long",
      });
      await sendMessage(
        config.telegram.targetChatId,
        `☀️ <b>좋은 아침입니다! - ${dateStr}</b>\n\n날씨 API 키가 설정되지 않았습니다.\n.env 파일에 WEATHER_API_KEY를 추가해주세요.`,
        { parseMode: "HTML" }
      );
      return;
    }

    const weather = await fetchWeather();
    const message = buildWeatherMessage(weather);
    await sendMessage(config.telegram.targetChatId, message, { parseMode: "HTML" });
  },
};
