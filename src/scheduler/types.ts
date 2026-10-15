export interface ScheduleJob {
  name: string;
  cronExpression: string;
  timezone: string;
  execute: () => Promise<void>;
  enabled: boolean;
}
