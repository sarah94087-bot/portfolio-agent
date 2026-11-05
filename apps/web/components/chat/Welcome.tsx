"use client";

import { useRef, useState } from "react";

import { CompassIcon, JobIcon, LayersIcon, StarIcon } from "@/components/ui/icons";
import { Composer, type ComposerMode, type ComposerStrings } from "./Composer";

// One tone per starter, in the design's order: ink, stone, salmon, accent (the job check).
const starterStyles = [
  { card: "bg-tint-ink text-on-ink", plate: "bg-badge-plate text-on-rose", Icon: StarIcon },
  { card: "bg-tint-stone text-on-stone", plate: "bg-badge-plate text-on-stone", Icon: LayersIcon },
  { card: "bg-tint-salmon text-on-salmon", plate: "bg-badge-plate text-on-salmon", Icon: CompassIcon },
  { card: "bg-accent text-on-accent", plate: "bg-badge-plate-on-accent text-on-accent", Icon: JobIcon },
];

type Props = {
  lang: string;
  starters: string[];
  startersLabel: string;
  composer: ComposerStrings;
  privacy: React.ReactNode;
};

// S1: starter questions and the composer share state, so a starter can fill or switch the composer.
// Sending is wired to the agent in M5; until then the composer is complete but has no handler.
export function Welcome({ lang, starters, startersLabel, composer, privacy }: Props) {
  const [mode, setMode] = useState<ComposerMode>("question");
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function pick(index: number) {
    if (index === starters.length - 1) {
      setMode("job");
      setValue("");
    } else {
      setMode("question");
      setValue(starters[index]);
    }
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  return (
    <>
      <ul aria-label={startersLabel} className="mt-5 grid grid-cols-1 gap-2 md:mt-7 md:grid-cols-2 md:gap-3">
        {starters.map((text, i) => {
          const s = starterStyles[i];
          return (
            <li key={text} className="flex">
              <button
                type="button"
                onClick={() => pick(i)}
                className={`flex min-h-14 w-full items-center gap-3 rounded-[12px] px-3.5 py-3 text-start text-[16px] font-bold leading-[1.35] transition-[filter] duration-(--dur-fast) hover:brightness-95 md:flex-col md:items-start md:gap-3.5 md:rounded-lg md:px-[18px] md:pb-[18px] md:pt-4 md:text-[19px] md:leading-[1.4] dark:hover:brightness-110 ${s.card}`}
              >
                <span className={`flex size-8 flex-none items-center justify-center rounded-[9px] md:size-[34px] md:rounded-md ${s.plate}`}>
                  <s.Icon size={18} />
                </span>
                {text}
              </button>
            </li>
          );
        })}
      </ul>

      {/* On mobile the composer sticks to the bottom, as in the design; on desktop it follows the cards. */}
      <div className="sticky bottom-0 -mx-4 mt-auto bg-surface px-4 pb-[max(18px,env(safe-area-inset-bottom))] pt-3 md:static md:mx-0 md:mt-6 md:bg-transparent md:p-0">
        <Composer
          ref={inputRef}
          lang={lang}
          t={composer}
          mode={mode}
          value={value}
          onModeChange={(m) => {
            setMode(m);
            requestAnimationFrame(() => inputRef.current?.focus());
          }}
          onChange={setValue}
        />
        <p className="mt-2.5 text-[12.5px] leading-[1.5] text-text-muted md:mt-4 md:text-small">{privacy}</p>
      </div>
    </>
  );
}
