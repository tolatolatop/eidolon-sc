import { buttonVariants } from "@/components/ui/button";
import { copy } from "@/i18n";

import { LandingEntry } from "./LandingEntry";

/** A text-only entrance: the three actual exercises form the page's reading rhythm. */
export function PrivateLanding({ isSignedIn }: { isSignedIn: boolean }) {
  const t = copy.privateLanding;
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-6 md:px-12">
        <a href="/" className="text-body font-semibold focus-visible:outline-2 focus-visible:outline-ring">{copy.app.name}</a>
        <span className="text-meta text-muted-foreground">{t.label}</span>
      </header>
      <main className="mx-auto grid max-w-6xl gap-12 px-6 py-12 md:grid-cols-2 md:gap-20 md:px-12 md:py-24">
        <section className="flex flex-col items-start gap-6">
          <p className="text-subtitle text-muted-foreground">{t.world} / {t.character}</p>
          <h1 className="whitespace-pre-line text-4xl leading-tight font-semibold tracking-tight md:text-5xl">{t.title}</h1>
          <p className="max-w-md text-body leading-relaxed text-muted-foreground">{t.intro}</p>
          <p className="text-subtitle">{t.format}</p>
          <LandingEntry isSignedIn={isSignedIn} label={isSignedIn ? copy.landing.continue : t.enter} className={buttonVariants({ size: "lg" })} />
          <p className="text-subtitle text-muted-foreground">{t.instruction}</p>
        </section>
        <section aria-labelledby="practice-heading" className="flex flex-col gap-5 md:pt-2">
          <h2 id="practice-heading" className="text-header">{t.practiceTitle}</h2>
          <ol className="divide-y border-y">
            {t.practices.map((practice, index) => (
              <li key={practice.title} className="grid grid-cols-[2rem_1fr] gap-3 py-6">
                <span className="pt-1 text-meta text-muted-foreground" aria-hidden="true">{index + 1} / 3</span>
                <div className="flex flex-col gap-2">
                  <h3 className="text-row-name">{practice.title}</h3>
                  <p className="text-body leading-relaxed text-muted-foreground">{practice.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="text-subtitle leading-relaxed text-muted-foreground">{t.practiceHint}</p>
        </section>
      </main>
      <footer className="mx-auto flex max-w-6xl flex-col gap-4 px-6 pb-10 md:px-12">
        <p className="max-w-3xl text-subtitle leading-relaxed text-muted-foreground">{t.scope}</p>
        <div className="flex gap-5 text-subtitle text-muted-foreground">
          <a href="/privacy" className="underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-ring">{copy.legal.privacy}</a>
          <a href="/terms" className="underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-ring">{copy.legal.terms}</a>
        </div>
      </footer>
    </div>
  );
}
