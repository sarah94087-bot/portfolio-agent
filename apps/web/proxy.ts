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

// docs/09-security-privacy.md, section 5, and ADR-0020. The nonce is new on every request, so a
// script the page did not send cannot run; `strict-dynamic` lets the scripts that carry it load
// the page's chunks, Mermaid's among them. Styles stay open to inline: Mermaid puts a <style> in
// every SVG, and a style cannot run code.
function contentSecurityPolicy(nonce: string) {
  const dev = process.env.NODE_ENV === "development"; // React's debugging and hot reload
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self'${dev ? " ws:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasLocale = locales.some((l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`));
  // A file's address has no language. One that does not exist is a 404 page, so it gets the policy.
  if (hasLocale || pathname.includes(".") || pathname.startsWith("/_next/")) {
    const policy = contentSecurityPolicy(Buffer.from(crypto.randomUUID()).toString("base64"));
    // On the request too: that is where the renderer reads the nonce from.
    const headers = new Headers(request.headers);
    headers.set("Content-Security-Policy", policy);
    const response = NextResponse.next({ request: { headers } });
    response.headers.set("Content-Security-Policy", policy);
    return response;
  }

  const url = request.nextUrl.clone();
  url.pathname = `/${preferredLocale(request.headers.get("accept-language"))}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Skip the backend (/api is routed to FastAPI by vercel.json) and the files that exist, so they
  // stay on the CDN with no function call.
  matcher: ["/((?!api/|_next/static/[^?]+\\.(?:js|css|woff2?)$|favicon\\.ico$|cv/).*)"],
};
