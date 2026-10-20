"use client";

import { useEffect, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { SettingsSection } from "@/components/app/SettingsSection";
import { useDirectory } from "@/components/conversations/ConversationDirectory";
import { Alert, AlertAction, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { copy } from "@/i18n";
import {
  getAccount,
  getSignInOptions,
  unlinkSignInMethod,
  type Account,
  type SignInOptions,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS, linkUrl, signInFailure, type Provider } from "@/lib/signIn";
import { CloseIcon, SuccessIcon } from "@/theme/icons";

const t = copy.settings.signIn;

/** 用户登录用的身份：绑定和解绑。退出登录是另一节（SignOutSettings），跟这里分开。解绑后告诉设置的 layout，
 * 外壳持有的登录的用户也换上新的，一级「登录与数据」的摘要跟着变。 */
export function SignInSettings() {
  const [account, setAccount] = useState<Account | null>(null);
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  // 去绑定是整页跳到后端、离开导航外壳：通话中先问会不会挂断。
  const { guard, accountChanged } = useDirectory();

  useEffect(() => {
    // 绑定完一个身份回到这里：说一声结果。
    const params = new URLSearchParams(window.location.search);
    const linked = params.get("linked") as Provider | null;
    if (linked && linked in PROVIDER_LABELS) setNotice(t.linked(PROVIDER_LABELS[linked]));
    const refusal = signInFailure(params.get("error"));
    if (refusal) setFailure({ message: refusal, signedOut: false });
    getAccount().then(setAccount, (e) => setFailure(toFailure(e)));
    getSignInOptions().then(setOptions, () => {});
  }, []);

  async function unlink(provider: Provider) {
    setNotice(null);
    setFailure(null);
    try {
      await unlinkSignInMethod(provider);
      const account = await getAccount();
      setAccount(account);
      accountChanged(account);
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  const methods = account?.sign_in_methods ?? [];
  const linkable = (options?.providers ?? []).filter(
    (provider) => !methods.some((m) => m.provider === provider),
  );
  const onlyOne = methods.length <= 1;

  return (
    <SettingsSection title={t.title} description={t.hint}>
      {notice && (
        <Alert role="status">
          <SuccessIcon />
          <AlertTitle>{notice}</AlertTitle>
          <AlertAction>
            <Button variant="ghost" size="icon-xs" aria-label={copy.common.close} onClick={() => setNotice(null)}>
              <CloseIcon />
            </Button>
          </AlertAction>
        </Alert>
      )}
      {failure && <FailureNotice failure={failure} />}
      {methods.length > 0 && (
        <ul className="flex flex-col divide-y">
          {methods.map((method) => {
            const provider = method.provider;
            const label = provider === "private" ? copy.login.privatePassword : PROVIDER_LABELS[provider];
            const unlinkButton = (
              <Button
                variant="ghost"
                size="sm"
                aria-label={t.unlinkLabel(label)}
                disabled={onlyOne || provider === "private"}
                focusableWhenDisabled
                onClick={() => { if (provider !== "private") void unlink(provider); }}
              >
                {t.unlink}
              </Button>
            );
            return (
              <li key={method.provider} className="flex items-center gap-3 py-3">
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="text-row-name">{label}</span>
                  <span className="text-subtitle break-words text-muted-foreground">
                    {method.email ? `${method.display_name} · ${method.email}` : method.display_name}
                  </span>
                </div>
                {provider === "private" ? null : onlyOne ? (
                  // 禁用的按钮照样能拿到焦点（focusableWhenDisabled），键盘和指针都看得到为什么不能解绑。
                  <Tooltip>
                    <TooltipTrigger render={unlinkButton} />
                    <TooltipContent>{t.onlyMethod}</TooltipContent>
                  </Tooltip>
                ) : (
                  unlinkButton
                )}
              </li>
            );
          })}
        </ul>
      )}
      {linkable.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {linkable.map((provider) => (
            <Button key={provider} variant="outline" nativeButton={false} render={<a href={linkUrl(provider)} onClick={guard(linkUrl(provider), true)} />}>
              {t.link(PROVIDER_LABELS[provider])}
            </Button>
          ))}
        </div>
      )}
    </SettingsSection>
  );
}
