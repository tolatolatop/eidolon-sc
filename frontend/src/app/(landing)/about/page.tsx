import type { Metadata } from "next";
import { cookies } from "next/headers";

import { getCharacters, getLandingAssets, getSignInOptions, isSignedIn } from "@/lib/backend";

import { isProjectSekai } from "@/lib/work";

import { PrivateLanding } from "../PrivateLanding";
import { Landing } from "../Landing";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

/** `/about`：和 `/` 同一个落地页，但不把已登录的用户送走（设置页的「关于 Eidolon-SC」到这里），只是入口换成「继续」。 */
export default async function About() {
  if (isProjectSekai) return <PrivateLanding isSignedIn={await isSignedIn((await cookies()).toString())} />;
  const [signedIn, characters, signInOptions, assets] = await Promise.all([
    isSignedIn((await cookies()).toString()),
    getCharacters(),
    getSignInOptions(),
    getLandingAssets(),
  ]);
  return <Landing isSignedIn={signedIn} characters={characters} signInOptions={signInOptions} assets={assets} />;
}
