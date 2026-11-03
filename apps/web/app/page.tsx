import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-16">
      <h1 className="text-3xl font-semibold">הסוכן של שרה</h1>
      <p className="mt-4">בבנייה. השלב הנוכחי: M1, תשתית וניסויים.</p>
      <p className="mt-4">
        <Link className="underline" href="/spike">
          ניסוי S1: הזרמה מהשרת לדפדפן
        </Link>
      </p>
    </main>
  );
}
