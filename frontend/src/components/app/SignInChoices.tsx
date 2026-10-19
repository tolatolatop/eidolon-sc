"use client";

import { useId, useState, type FormEvent } from "react";

import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { AppLink } from "@/components/app/AppLink";
import { Button } from "@/components/ui/button";
import { copy } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";
import { privateLogin, type SignInOptions } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PROVIDER_LABELS, signInUrl } from "@/lib/signIn";

const t = copy.login;

/**
 * 登录组件：后端提供的登录方式（第一种是主按钮）、登录即同意的说明，部署者一种都没配时的提示。
 * 登录页和落地页的登录面板共用它；`options` 还没取到时只有同意说明。
 */
export function SignInChoices({ options, className }: { options: SignInOptions | null; className?: string }) {
  return (
    <section aria-label={t.signInRegion} className={cn("flex flex-col gap-3", className)}>
      {options?.providers.map((provider, i) => (
        // 登录要整页跳到后端的 OAuth 入口，用普通的 <a>，不走客户端路由。
        <Button
          key={provider}
          variant={i === 0 ? "default" : "outline"}
          size="lg"
          nativeButton={false}
          render={<a href={signInUrl(provider)} />}
          className="w-full"
        >
          {t.signInWith(PROVIDER_LABELS[provider])}
        </Button>
      ))}
      {options?.private_login && <PrivateSignInForm />}
      {options && options.providers.length === 0 && !options.dev_login && !options.private_login && (
        <p className="text-body text-muted-foreground">{t.noProviders}</p>
      )}
      <p className="text-sm text-muted-foreground">
        {interpolate(t.agreement, {
          privacy: (
            <AppLink key="privacy" href="/privacy">
              {copy.legal.privacy}
            </AppLink>
          ),
          terms: (
            <AppLink key="terms" href="/terms">
              {copy.legal.terms}
            </AppLink>
          ),
        })}
      </p>
    </section>
  );
}

/** Shared by the landing dialog and the dedicated login page; secrets stay in component state. */
function PrivateSignInForm() {
  const id = useId();
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      await privateLogin(password);
      setPassword("");
      window.location.assign("/conversations");
    } catch (cause) {
      setPassword("");
      setError(cause instanceof Error ? cause.message : t.privateFailed);
      setSubmitting(false);
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field data-invalid={!!error || undefined}>
        <FieldLabel htmlFor={id}>{t.privatePassword}</FieldLabel>
        <Input id={id} type="password" autoComplete="off" value={password}
          onChange={(event) => setPassword(event.target.value)} disabled={submitting}
          aria-invalid={!!error || undefined} aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`} required />
        <FieldDescription id={`${id}-hint`}>{t.privateHint}</FieldDescription>
        {error && <FieldError id={`${id}-error`} role="alert">{error}</FieldError>}
      </Field>
      <Button type="submit" disabled={submitting || !password}>{submitting ? t.privateSubmitting : t.privateSubmit}</Button>
    </form>
  );
}
