import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const typographyVariants = cva("", {
  variants: {
    variant: {
      h1: "text-4xl font-semibold tracking-tight",
      h2: "text-3xl font-semibold tracking-tight",
      h3: "text-2xl font-semibold tracking-tight",
      h4: "text-xl font-semibold tracking-tight",
      h5: "text-lg font-medium",
      h6: "text-base font-medium",
      lead: "text-lg text-muted-foreground",
      p: "text-base leading-relaxed",
      large: "text-lg font-medium",
      small: "text-sm leading-normal",
      muted: "text-sm text-muted-foreground",
      label: "text-sm font-medium leading-none",
    },
  },
  defaultVariants: {
    variant: "p",
  },
});

type VariantType = NonNullable<
  VariantProps<typeof typographyVariants>["variant"]
>;

type ElementType =
  | "h1"
  | "h2"
  | "h3"
  | "h4"
  | "h5"
  | "h6"
  | "p"
  | "span"
  | "div"
  | "label";

const variantElementMap: Record<VariantType, ElementType> = {
  h1: "h1",
  h2: "h2",
  h3: "h3",
  h4: "h4",
  h5: "h5",
  h6: "h6",
  lead: "p",
  p: "p",
  large: "p",
  small: "p",
  muted: "p",
  label: "label",
};

export interface TypographyProps
  extends
    React.HTMLAttributes<HTMLElement>,
    VariantProps<typeof typographyVariants> {
  asChild?: boolean;
  as?: ElementType;
}

const Typography = React.forwardRef<HTMLElement, TypographyProps>(
  (
    { className, variant = "p", asChild = false, as, children, ...props },
    ref
  ) => {
    const defaultElement = variantElementMap[variant as VariantType] || "p";
    const Element = as || defaultElement;

    if (asChild) {
      return (
        <Slot
          className={cn(typographyVariants({ variant }), className)}
          ref={ref}
          {...props}
        >
          {children}
        </Slot>
      );
    }

    return React.createElement(
      Element,
      {
        className: cn(typographyVariants({ variant }), className),
        ref,
        ...props,
      },
      children
    );
  }
);

Typography.displayName = "Typography";

export { Typography, typographyVariants };
