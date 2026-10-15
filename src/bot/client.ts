import TelegramBot from "node-telegram-bot-api";
import { config } from "../config";
import { logger } from "../logger";

let instance: TelegramBot | null = null;

export function getBotClient(): TelegramBot {
  if (!instance) {
    instance = new TelegramBot(config.telegram.botToken);
    logger.info("Telegram bot client initialized");
  }
  return instance;
}
