import type { Metadata } from "next";
import "./globals.css";

// Visual design comes from Claude Design before M5 (docs/05-architecture.md, section 11).
// Until then the layout stays neutral and only sets language and direction.
export const metadata: Metadata = {
  title: "הסוכן של שרה",
  description: "סוכן AI שעונה על שאלות על הניסיון של שרה הלוי, עם מקורות לכל טענה",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="he" dir="rtl" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
