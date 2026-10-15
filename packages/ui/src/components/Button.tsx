"use client";

import { Button as AriaButton, type ButtonProps as AriaButtonProps } from "react-aria-components";

export type ButtonVariant = "primary" | "secondary" | "ghost";

export interface ButtonProps extends AriaButtonProps {
  variant?: ButtonVariant;
}

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-accent bg-accent text-on-accent",
  secondary: "border-line-strong bg-transparent text-text hover:bg-raised",
  ghost: "border-transparent bg-transparent text-muted hover:bg-raised hover:text-text",
};

/** Button on React Aria: keyboard, press and focus handling included. Square corners. */
export function Button({ variant = "secondary", className, ...props }: ButtonProps) {
  const base =
    "inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-control border px-3.5 text-xs " +
    "outline-none data-[disabled]:cursor-not-allowed data-[disabled]:text-faint " +
    "data-[focus-visible]:outline-1 data-[focus-visible]:outline-offset-2 data-[focus-visible]:outline-accent";
  return (
    <AriaButton
      {...props}
      className={
        typeof className === "function"
          ? (state) => `${base} ${VARIANTS[variant]} ${className(state)}`
          : `${base} ${VARIANTS[variant]} ${className ?? ""}`
      }
    />
  );
}
