import Link from "next/link";
import { notFound } from "next/navigation";

import { Welcome } from "@/components/chat/Welcome";
import { Header } from "@/components/ui/Header";
import { getDictionary, hasLocale } from "./dictionaries";

// S1, the welcome screen (Claude Design boards "Main", "S1-EN", "S1-Mobile-EN-Dark").
export default async function WelcomePage({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const t = getDictionary(lang);
  const w = t.welcome;

  return (
    <>
      <Header lang={lang} t={t.header} />
      <main className="flex flex-1 flex-col px-4 pt-6 md:items-center md:pt-12">
        <div className="mx-auto flex w-full max-w-measure flex-1 flex-col md:flex-none">
          <p className="mb-2 text-[13px] font-bold text-accent md:mb-3 md:text-[14px]">{w.eyebrow}</p>
          <h1 className="text-[28px] font-extrabold leading-[1.25] tracking-[-0.01em] md:text-h1 md:leading-[1.3]">
            {w.titleLead}{" "}
            <span className="rounded-sm bg-tint-ink px-1.5 text-on-ink [box-decoration-break:clone] md:px-2">
              {w.titleHighlight}
            </span>
            <br className="hidden md:block" /> {w.titleRest}
          </h1>
          <p className="mt-3 text-[16px] leading-[1.6] text-text-muted md:mt-4 md:text-[19px] md:leading-[1.75]">{w.lede}</p>

          <Welcome
            lang={lang}
            starters={w.starters}
            startersLabel={w.startersLabel}
            composer={t.composer}
            privacy={
              <>
                {w.privacy}{" "}
                <Link href={`/${lang}/privacy`} className="text-accent underline underline-offset-3">
                  {w.privacyLink}
                </Link>
              </>
            }
          />
        </div>
      </main>
    </>
  );
}
