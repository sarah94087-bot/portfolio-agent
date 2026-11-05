import { NextResponse, type NextRequest } from "next/server";

// Kept in sync with app/[lang]/dictionaries.ts. Proxy runs apart from the render code,
// so it does not import app modules.
const locales = ["he", "en"];
const defaultLocale = "he";

// The first of our locales that the browser lists, in its own order of preference.
function preferredLocale(acceptLanguage: string | null): string {
  if (!acceptLanguage) return defaultLocale;
  const ranked = acceptLanguage
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { lang: tag.toLowerCase().split("-")[0], q: q ? Number(q) : 1 };
    })
    .sort((a, b) => b.q - a.q);
  return ranked.find((r) => locales.includes(r.lang))?.lang ?? defaultLocale;
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasLocale = locales.some((l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`));
  if (hasLocale) return;

  const url = request.nextUrl.clone();
  url.pathname = `/${preferredLocale(request.headers.get("accept-language"))}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Skip the backend (/api is routed to FastAPI by vercel.json), Next internals and files.
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
