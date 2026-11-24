import Link from "next/link";
import { notFound } from "next/navigation";

import { Chat } from "@/components/chat/Chat";
import { Header } from "@/components/ui/Header";
import { JsonLd } from "@/components/ui/JsonLd";
import { SITE_URL } from "@/lib/site";
import { getDictionary, hasLocale } from "./dictionaries";

// S1, the welcome screen (Claude Design boards "Main", "S1-EN", "S1-Mobile-EN-Dark"), which
// becomes S2, the conversation, at the first question (boards "A-S2", "S2-States", "S2-Mobile").
export default async function ChatPage({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const t = getDictionary(lang);
  const w = t.welcome;

  // Only what the page already says: the site's name, its language and whom it is about.
  // No profile links, until Sarah decides which ones to publish.
  const person = { "@type": "Person", "@id": `${SITE_URL}/#sarah-halevy`, name: "Sarah Halevy" };
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/${lang}#website`,
        url: `${SITE_URL}/${lang}`,
        name: t.meta.title,
        description: t.meta.description,
        inLanguage: lang,
        about: { "@id": person["@id"] },
      },
      person,
    ],
  };

  return (
    <>
      <JsonLd data={structuredData} />
      <Header lang={lang} t={t.header} />
      <main className="flex flex-1 flex-col px-4 pt-6 md:items-center md:pt-10">
        <div className="mx-auto flex w-full max-w-measure flex-1 flex-col">
          <Chat
            lang={lang}
            intro={
              <>
                <p className="mb-2 text-[13px] font-bold text-accent md:mb-3 md:text-[14px]">{w.eyebrow}</p>
                <h1 className="text-[28px] font-extrabold leading-[1.25] tracking-[-0.01em] md:text-h1 md:leading-[1.3]">
                  {w.titleLead}{" "}
                  <span className="rounded-sm bg-tint-ink px-1.5 text-on-ink [box-decoration-break:clone] md:px-2">
                    {w.titleHighlight}
                  </span>
                  <br className="hidden md:block" /> {w.titleRest}
                </h1>
                <p className="mt-3 text-[16px] leading-[1.6] text-text-muted md:mt-4 md:text-[19px] md:leading-[1.75]">{w.lede}</p>
              </>
            }
            starters={w.starters}
            startersLabel={w.startersLabel}
            composer={t.composer}
            chat={t.chat}
            agentName={t.header.agentName}
            agentLine={`${t.header.agentName} · ${t.header.aiTag}`}
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
      <section aria-labelledby="home-info" className="px-4 pb-16 pt-10 md:pt-14">
        <div className="mx-auto w-full max-w-measure">
          <h2 id="home-info" className="text-[20px] font-extrabold leading-[1.3] md:text-[22px]">
            {t.welcome.info.whatTitle}
          </h2>
          <p className="mt-2 text-[16px] leading-[1.7] text-text-muted">{t.welcome.info.what}</p>
          <h2 className="mt-8 text-[20px] font-extrabold leading-[1.3] md:text-[22px]">{t.welcome.info.askTitle}</h2>
          <p className="mt-2 text-[16px] leading-[1.7] text-text-muted">
            {t.welcome.info.askBefore}
            <Link href={`/${lang}/how-it-works`} className="text-accent underline underline-offset-3">
              {t.header.howItWorks}
            </Link>
            {t.welcome.info.askMiddle}
            <Link href={`/${lang}/quality`} className="text-accent underline underline-offset-3">
              {t.header.quality}
            </Link>
            {t.welcome.info.askAfter}
          </p>
        </div>
      </section>
    </>
  );
}
