"use client";

import { useId } from "react";

import { SettingsSection } from "@/components/app/SettingsSection";
import { useDirectory } from "@/components/conversations/ConversationDirectory";
import { Field, FieldContent, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { copy } from "@/i18n";
import { isProjectSekai, PRIVATE_WORK } from "@/lib/work";

const t = copy.settings.appearance;

/**
 * 设置「外观」：现在只有「SCSP 头像」（GLOSSARY.md「SCSP 头像」），记在这台设备上、按用户分开。
 * 值由导航外壳持有，一拨开关，登录后应用里的头像和一级「外观」的摘要都马上跟着换。
 */
export function AppearanceSettings() {
  const { account, appearance, changeAppearance } = useDirectory();
  const id = useId();

  if (!account) return null;
  if (isProjectSekai) return <SettingsSection><p className="text-body text-muted-foreground">{PRIVATE_WORK.appearance}</p></SettingsSection>;

  return (
    <SettingsSection>
      <FieldGroup>
        <Field orientation="horizontal">
          <FieldContent>
            <FieldLabel htmlFor={`${id}-scsp`}>{t.scspAvatars}</FieldLabel>
          </FieldContent>
          <Switch
            id={`${id}-scsp`}
            checked={appearance.scspAvatars}
            onCheckedChange={(scspAvatars) => changeAppearance({ ...appearance, scspAvatars })}
          />
        </Field>
      </FieldGroup>
    </SettingsSection>
  );
}
