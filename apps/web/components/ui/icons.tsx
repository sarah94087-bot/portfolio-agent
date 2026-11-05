// Inline stroke icons from the Claude Design boards. Decorative: the control carries the label.
// Icons with a direction carry `icon-dir` and are drawn pointing to inline-end in LTR;
// globals.css mirrors them in RTL.

type IconProps = { size?: number; className?: string };

function Svg({ size = 16, className, children, viewBox = "0 0 16 16", strokeWidth = 1.5 }: IconProps & {
  children: React.ReactNode;
  viewBox?: string;
  strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {children}
    </svg>
  );
}

export const SendIcon = ({ size = 18, className = "" }: IconProps) => (
  <Svg size={size} strokeWidth={1.7} className={`icon-dir ${className}`}>
    <path d="M2 8h11M9 4l4 4-4 4" />
  </Svg>
);

export const DownloadIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 2v8M4.5 7 8 10.5 11.5 7M3 13.5h10" />
  </Svg>
);

export const DocumentIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 2h5.5L12 4.5V14H4z" />
    <path d="M6 8h4M6 11h4" />
  </Svg>
);

export const BackIcon = ({ size = 16, className = "" }: IconProps) => (
  <Svg size={size} className={`icon-dir ${className}`}>
    <path d="M14 8H3M7 4 3 8l4 4" />
  </Svg>
);

// Starter-card icons (24px grid).
export const StarIcon = (p: IconProps) => (
  <Svg {...p} viewBox="0 0 24 24" strokeWidth={1.8}>
    <path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z" />
  </Svg>
);

export const LayersIcon = (p: IconProps) => (
  <Svg {...p} viewBox="0 0 24 24" strokeWidth={1.8}>
    <path d="m12 2 9 5-9 5-9-5zM3 12l9 5 9-5M3 16.5l9 5 9-5" />
  </Svg>
);

export const CompassIcon = (p: IconProps) => (
  <Svg {...p} viewBox="0 0 24 24" strokeWidth={1.8}>
    <circle cx="12" cy="12" r="9" />
    <path d="m15.5 8.5-2 5-5 2 2-5z" />
  </Svg>
);

export const JobIcon = (p: IconProps) => (
  <Svg {...p} viewBox="0 0 24 24" strokeWidth={1.8}>
    <path d="M6 3h8l4 4v14H6zM9 12h6M9 16h6" />
  </Svg>
);

// S2: the sources toggle, a spinner for the tool status, the fallback swap, close and retry.
export const ChevronIcon = ({ size = 14, className = "" }: IconProps) => (
  <Svg size={size} strokeWidth={1.6} className={className}>
    <path d="M3 6l5 5 5-5" />
  </Svg>
);

export const SpinnerIcon = ({ size = 16, className = "" }: IconProps) => (
  <Svg size={size} strokeWidth={2} className={`text-accent motion-safe:animate-spin ${className}`}>
    <path d="M8 2a6 6 0 1 0 6 6" />
  </Svg>
);

export const SwapIcon = ({ size = 11, className = "" }: IconProps) => (
  <Svg size={size} strokeWidth={1.8} className={className}>
    <path d="M2 5h9l-2-2M14 11H5l2 2" />
  </Svg>
);

export const CloseIcon = ({ size = 16, className = "" }: IconProps) => (
  <Svg size={size} strokeWidth={1.7} className={className}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Svg>
);

export const RetryIcon = ({ size = 15, className = "" }: IconProps) => (
  <Svg size={size} strokeWidth={1.7} className={className}>
    <path d="M13 8a5 5 0 1 1-1.5-3.5M13 2.5v3h-3" />
  </Svg>
);
