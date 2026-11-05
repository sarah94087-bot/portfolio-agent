import Link from "next/link";

type Variant = "primary" | "secondary" | "ghost" | "icon";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-bold text-ui transition-colors duration-(--dur-fast) disabled:cursor-not-allowed disabled:opacity-45";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-hover",
  secondary: "border-[1.5px] border-border-strong text-text hover:bg-surface-sunken",
  ghost: "border border-border text-text hover:bg-surface-sunken",
  // Square, 40px: at least the 24px target WCAG 2.2 asks for, close to the 44px comfort size.
  icon: "size-10 bg-accent text-on-accent hover:bg-accent-hover",
};

const sizes: Record<Variant, string> = {
  primary: "px-4 py-2",
  secondary: "px-3.5 py-1.5",
  ghost: "px-3 py-1.5",
  icon: "",
};

export function buttonClass(variant: Variant = "primary", extra = "") {
  return `${base} ${variants[variant]} ${sizes[variant]} ${extra}`;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant };

export function Button({ variant = "primary", className = "", type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, className)} {...rest} />;
}

type LinkButtonProps = React.ComponentProps<typeof Link> & { variant?: Variant };

export function LinkButton({ variant = "secondary", className = "", ...rest }: LinkButtonProps) {
  return <Link className={buttonClass(variant, className)} {...rest} />;
}
