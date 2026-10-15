import winston from "winston";
import path from "path";
import { config } from "../config";

const { combine, timestamp, printf, colorize, errors } = winston.format;

const logFormat = printf(({ level, message, timestamp, stack }) => {
  return `${timestamp} [${level}]: ${stack ?? message}`;
});

export const logger = winston.createLogger({
  level: config.app.logLevel,
  format: combine(
    timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
    errors({ stack: true }),
    logFormat
  ),
  transports: [
    new winston.transports.Console({
      format: combine(colorize(), timestamp({ format: "YYYY-MM-DD HH:mm:ss" }), errors({ stack: true }), logFormat),
    }),
    new winston.transports.File({
      filename: path.join("logs", "error.log"),
      level: "error",
    }),
    new winston.transports.File({
      filename: path.join("logs", "combined.log"),
    }),
  ],
});
