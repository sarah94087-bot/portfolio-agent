// Small label: the "AI agent" badge, later "fallback model" and "citation removed".
type Tone = "accent" | "fallback" | "removed";

const tones: Record<Tone, string> = {
  accent: "bg-accent text-on-accent",
  fallback: "bg-fallback-bg text-fallback",
  // Removed is dashed and neutral, so it reads as information, not as an error.
  removed: "border border-dashed border-removed text-removed",
};

export function Tag({ tone = "accent", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-sm px-2 text-small font-bold ${tones[tone]}`}>
      {children}
    </span>
  );
}
