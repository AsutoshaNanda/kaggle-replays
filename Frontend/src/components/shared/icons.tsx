// Inline stroke-SVG icon set (no dependency). Replaces all emojis app-wide.
// Each icon inherits `currentColor` and takes an optional `size` (px).

import type { JSX, SVGProps } from 'react'

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number
}

function base({ size = 18, ...props }: IconProps): IconProps {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.75,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
    ...props,
  } as IconProps
}

export function BoltIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" /></svg>
}
export function TrophyIcon(p: IconProps): JSX.Element {
  return (
    <svg {...base(p)}>
      <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4Z" />
      <path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3" />
    </svg>
  )
}
export function DownloadIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
}
export function InboxIcon(p: IconProps): JSX.Element {
  return (
    <svg {...base(p)}>
      <path d="M4 13h4l1 3h6l1-3h4" />
      <path d="M5 13 7 4h10l2 9v5a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-5Z" />
    </svg>
  )
}
export function CheckIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="m5 13 4 4L19 7" /></svg>
}
export function XIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M6 6 18 18M18 6 6 18" /></svg>
}
export function AlertIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></svg>
}
export function SunIcon(p: IconProps): JSX.Element {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" />
    </svg>
  )
}
export function MoonIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" /></svg>
}
export function TargetIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="0.5" /></svg>
}
export function PackageIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4 7.5 8 4.5 8-4.5M12 21v-9" /></svg>
}
export function LockIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
}
export function GlobeIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18Z" /></svg>
}
export function ArrowRightIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M5 12h14m0 0-6-6m6 6-6 6" /></svg>
}
export function ArrowLeftIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M19 12H5m0 0 6 6m-6-6 6-6" /></svg>
}
export function ArrowUpRightIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M7 17 17 7m0 0H8m9 0v9" /></svg>
}
export function SparkleIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M12 3v18M3 12h18M6 6l12 12M18 6 6 18" /></svg>
}
export function ChartIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><path d="M4 20V10m5 10V4m5 16v-7m5 7V8" /></svg>
}
export function MedalIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><circle cx="12" cy="15" r="5" /><path d="M9 10 7 3h10l-2 7M11 15h2" /></svg>
}
export function UserIcon(p: IconProps): JSX.Element {
  return <svg {...base(p)}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>
}
