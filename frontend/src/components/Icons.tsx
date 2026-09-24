/**
 * Inline-SVGs statt Icon-Paket: acht Symbole, alle auf demselben 16er-Raster,
 * 1,5px Strichstärke. Weniger Abhängigkeiten und ein konsistenter Strich.
 */
import type { ReactNode } from "react";

type Props = { className?: string };

const base = "h-4 w-4 shrink-0";

function Svg({ children, className }: Props & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? base}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const IconPin = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M8 10v4M5 3h6l-1 4.5 2 2.5H4l2-2.5L5 3Z" />
  </Svg>
);

export const IconDice = ({ className }: Props) => (
  <Svg className={className}>
    <rect x="2.5" y="2.5" width="11" height="11" rx="2.5" />
    <circle cx="6" cy="6" r=".7" fill="currentColor" />
    <circle cx="10" cy="10" r=".7" fill="currentColor" />
  </Svg>
);

export const IconPlus = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M8 3.5v9M3.5 8h9" />
  </Svg>
);

export const IconCheck = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M3 8.5 6.5 12 13 4.5" />
  </Svg>
);

export const IconClose = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Svg>
);

export const IconChevronLeft = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M10 3.5 5.5 8l4.5 4.5" />
  </Svg>
);

export const IconChevronRight = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M6 3.5 10.5 8 6 12.5" />
  </Svg>
);

export const IconWarn = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M8 2.5 14.5 13.5h-13L8 2.5ZM8 6.5v3M8 11.5v.01" />
  </Svg>
);

export const IconLeftover = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M2.5 6.5h11M4 6.5v6a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-6M6.5 4.5 8 2.5l1.5 2" />
  </Svg>
);

export const IconCart = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M2 3h2l1.6 7.2a1 1 0 0 0 1 .8h5.2a1 1 0 0 0 1-.8L14 6H5" />
    <circle cx="6.5" cy="13.5" r=".9" />
    <circle cx="12" cy="13.5" r=".9" />
  </Svg>
);

export const IconBook = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M3 3.5h4a2 2 0 0 1 2 2v8a1.5 1.5 0 0 0-1.5-1.5H3v-8.5ZM13 3.5H9.5a2 2 0 0 0-1.5.7v9.3a1.5 1.5 0 0 1 1.5-1.5H13v-8.5Z" />
  </Svg>
);

export const IconTag = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M8.5 2.5H13v4.5l-6 6L2 8l6.5-5.5Z" />
    <circle cx="10.5" cy="5.5" r=".8" />
  </Svg>
);

export const IconGear = ({ className }: Props) => (
  <Svg className={className}>
    <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" />
    <circle cx="6" cy="4.5" r="1.4" fill="var(--icon-bg, #fff)" />
    <circle cx="10.5" cy="8" r="1.4" fill="var(--icon-bg, #fff)" />
    <circle cx="5" cy="11.5" r="1.4" fill="var(--icon-bg, #fff)" />
  </Svg>
);
