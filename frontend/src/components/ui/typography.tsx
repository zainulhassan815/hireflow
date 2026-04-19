import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// F90.b — editorial-serious type scale.
// h1–h3 carry the display face (Fraunces) with tuned leading + negative
// tracking so headlines feel tight and confident. h4–h6 stay on the
// body sans (Inter) — sub-headline territory where the serif would
// read as fussy.
const typographyVariants = cva("", {
  variants: {
    variant: {
      h1: "font-display text-4xl font-semibold leading-[1.1] tracking-[-0.02em]",
      h2: "font-display text-3xl font-semibold leading-[1.15] tracking-[-0.02em]",
      h3: "font-display text-2xl font-semibold leading-[1.2] tracking-[-0.015em]",
      h4: "text-xl font-semibold leading-[1.25] tracking-[-0.01em]",
      h5: "text-lg font-medium leading-[1.35]",
      h6: "text-base font-medium leading-[1.4]",
      lead: "text-lg leading-[1.6] text-muted-foreground",
      p: "text-base leading-[1.65]",
      large: "text-lg font-medium leading-[1.4]",
      small: "text-sm leading-[1.5]",
      muted: "text-sm leading-[1.5] text-muted-foreground",
      label: "text-sm font-medium leading-none tracking-[0.01em]",
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
