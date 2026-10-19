"use client";

import { useEffect, useState } from "react";

import { AppLink } from "@/components/app/AppLink";
import { FailureNotice } from "@/components/app/FailureNotice";
import { SignInChoices } from "@/components/app/SignInChoices";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { copy } from "@/i18n";
import { getSignInOptions, type SignInOptions } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.landing;

/**
 * 落地页里弹出的登录面板：和登录页同一个登录组件。登录被拒的原因和开发登录仍在 `/login`，
 * 后端开着开发登录时这里给一个去那里的链接。
 */
export default function SignInPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    getSignInOptions().then(setOptions, (e) => setFailure(toFailure(e)));
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t.panelTitle}</DialogTitle>
        </DialogHeader>
        <SignInChoices options={options} />
        {options?.dev_login && !options.private_login && (
          <AppLink href="/login" isStandalone className="justify-self-start">
            {t.devSignIn}
          </AppLink>
        )}
        {failure && <FailureNotice failure={failure} />}
      </DialogContent>
    </Dialog>
  );
}
