export function Logo({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      className={className}
    >
      <circle cx="32" cy="32" r="19" fill="none" stroke="currentColor" strokeWidth="5" />
      <circle cx="45.5" cy="18.5" r="5.5" fill="currentColor" />
    </svg>
  );
}
