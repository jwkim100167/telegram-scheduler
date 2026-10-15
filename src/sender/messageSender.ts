import { getBotClient } from "../bot/client";
import { logger } from "../logger";

export interface MessageOptions {
  parseMode?: "HTML" | "Markdown" | "MarkdownV2";
  disableNotification?: boolean;
}

const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;

export async function sendMessage(
  chatId: string | number,
  message: string,
  options: MessageOptions = {}
): Promise<void> {
  const bot = getBotClient();

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      await bot.sendMessage(chatId, message, {
        parse_mode: options.parseMode,
        disable_notification: options.disableNotification,
      });
      logger.info(`Message sent to ${chatId} (attempt ${attempt})`);
      return;
    } catch (error) {
      const isLastAttempt = attempt === MAX_RETRIES;
      if (isLastAttempt) {
        logger.error(`Failed to send message to ${chatId} after ${MAX_RETRIES} attempts`, error);
        throw error;
      }
      const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
      logger.warn(`Send failed (attempt ${attempt}/${MAX_RETRIES}), retrying in ${delay}ms...`);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
}
