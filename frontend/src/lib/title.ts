const TITLE_WHITESPACE = /\s/;

export const TITLE_MAX = 30;
export const INTRO_MAX = 150;

export function validateTitle(title: string): string {
  const trimmed = (title ?? "").trim();
  if (!trimmed) {
    throw new Error("名称不能为空");
  }
  if (TITLE_WHITESPACE.test(trimmed)) {
    throw new Error("名称不能包含空白字符");
  }
  if (trimmed.length > TITLE_MAX) {
    throw new Error("名称最多 30 个字符");
  }
  return trimmed;
}

export function validateIntro(intro: string): string {
  const value = intro ?? "";
  if (!value.trim()) {
    throw new Error("简介不能为空");
  }
  if (value.length > INTRO_MAX) {
    throw new Error("简介最多 150 个字符");
  }
  return value;
}
