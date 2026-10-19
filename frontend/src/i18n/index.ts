import { isProjectSekai } from "@/lib/work";

import { projectSekai } from "./projectSekai";
import { zh } from "./zh";

/** 一种界面语言的全部文案：结构以简体中文为准，以后加的语言要有同样的键。 */
export type Messages = typeof zh;

/** 当前界面语言的文案。这次只上线简体中文（spec「文案集中管理」）。 */
export const copy: Messages = isProjectSekai ? projectSekai : zh;
