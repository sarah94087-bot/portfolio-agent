import { buttonClass } from "@/components/ui/Button";
import { DownloadIcon } from "@/components/ui/icons";
import { CV_HREF, CV_NAME } from "@/lib/site";
import type { ChatStrings } from "./AgentMessage";

// S7's page state (board S7-S8, "מצב עמוד") for the kill switch: the agent is off, the CV is
// the way to reach Sarah. No "leave a message" button, since there is no contact form yet.
export function Paused({ t, heading }: { t: ChatStrings["paused"]; heading: "h1" | "h2" }) {
  const Heading = heading;
  return (
    <section role="status" className="flex flex-col items-start gap-4 py-8 md:py-14">
      <span aria-hidden="true" className="flex size-11 items-center justify-center rounded-[12px] bg-tint-salmon text-on-salmon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" focusable="false">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
      </span>
      <Heading className="text-[28px] font-extrabold leading-[1.3] md:text-[30px]">{t.title}</Heading>
      <p className="text-[16px] leading-[1.7] text-text-muted md:text-[18px] md:leading-[1.75]">{t.body}</p>
      <a href={CV_HREF} download={CV_NAME} className={buttonClass("primary", "min-h-[42px]")}>
        <DownloadIcon />
        {t.cv}
      </a>
    </section>
  );
}
