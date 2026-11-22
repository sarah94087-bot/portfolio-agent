// Structured data for search engines. A JSON-LD block is data, not code, so the CSP's script-src
// (which needs a nonce for every script) does not apply to it. "<" is escaped so that text from
// the dictionary can never close the tag.
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}
