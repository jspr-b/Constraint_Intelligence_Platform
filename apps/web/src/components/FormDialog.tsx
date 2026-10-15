"use client";

import { useId, type FormEvent, type ReactNode } from "react";
import { Dialog, DialogTrigger, Heading, Modal, ModalOverlay } from "react-aria-components";
import { Button, MicroLabel } from "@cip/ui";

/** A button that opens a modal form. `onSubmit` returns an error message, or null to close. */
export function FormDialog({
  label,
  title,
  submitLabel,
  cancelLabel,
  onSubmit,
  error,
  children,
  variant = "secondary",
}: {
  label: string;
  title: string;
  submitLabel: string;
  cancelLabel: string;
  onSubmit: (form: FormData) => Promise<boolean>;
  error: string | null;
  children: ReactNode;
  variant?: "primary" | "secondary";
}) {
  return (
    <DialogTrigger>
      <Button variant={variant}>{label}</Button>
      <ModalOverlay
        isDismissable
        className="fixed inset-0 z-40 flex items-center justify-center bg-text/30 p-4"
      >
        <Modal className="w-full max-w-md rounded-panel border border-line-strong bg-surface p-6 outline-none">
          <Dialog className="outline-none">
            {({ close }) => (
              <form
                className="flex flex-col gap-4"
                onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  if (await onSubmit(new FormData(event.currentTarget))) close();
                }}
              >
                <Heading slot="title" className="m-0 text-base font-medium">
                  {title}
                </Heading>
                {children}
                {error && (
                  <p role="alert" className="m-0 text-sm text-bad">
                    {error}
                  </p>
                )}
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onPress={close}>
                    {cancelLabel}
                  </Button>
                  <Button type="submit" variant="primary">
                    {submitLabel}
                  </Button>
                </div>
              </form>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}

export const FIELD =
  "min-h-10 rounded-control border border-line-strong bg-surface px-3 text-sm text-text outline-none focus-visible:outline-1 focus-visible:outline-accent";

/** A form field with a real <label for>, so a select's options never end up in its name. */
export function Field({
  label,
  children,
  className = "flex flex-col gap-1.5",
}: {
  label: string;
  children: (id: string) => ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id}>
        <MicroLabel>{label}</MicroLabel>
      </label>
      {children(id)}
    </div>
  );
}
