import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";

dayjs.extend(relativeTime);
dayjs.extend(utc);

export function fmtAbs(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm:ss.SSS");
}

export function fmtRel(iso: string | null | undefined): string {
  if (!iso) return "never";
  return dayjs(iso).fromNow();
}

export function shortHex(value: string | null | undefined, take = 12): string {
  if (!value) return "—";
  if (value.length <= take + 2) return value;
  return `${value.slice(0, take)}…`;
}
