/**
 * The mark.
 *
 * Two ideas, because this product only does two things.
 *
 * **The funnel.** Three bars narrowing downward — a national population
 * narrowing to the handful of patients a therapy is actually paid for. That
 * shape is the whole first half of the model, and it is the thing every user
 * of this tool draws on a whiteboard within two minutes of explaining it.
 *
 * **The delta.** The gap notched out of the bottom bar is the answer: budget
 * impact is a *difference* between two worlds, not a total. It is deliberately
 * a small gap between two large forms, because that is exactly the arithmetic —
 * a small number found between two large ones — and a mark that showed a big
 * dramatic wedge would be misrepresenting the product on the login screen.
 *
 * Drawn rather than imported: a logo that is one inline SVG costs no request,
 * cannot 404, inherits the theme's accent, and stays crisp at every size the
 * header wraps to.
 */

export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="BIET"
      className="brandmark"
    >
      <defs>
        <linearGradient id="biet-field" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--brand-1)" />
          <stop offset="100%" stopColor="var(--brand-2)" />
        </linearGradient>
      </defs>

      <rect width="32" height="32" rx="9" fill="url(#biet-field)" />

      {/* The funnel: three bars narrowing. Rounded ends so it reads as a
          diagram rather than a bar chart — this is a population narrowing,
          not a series of measurements. */}
      <rect x="7" y="8.5" width="18" height="3.4" rx="1.7" fill="#fff" opacity=".95" />
      <rect x="10" y="14.3" width="12" height="3.4" rx="1.7" fill="#fff" opacity=".72" />

      {/* The bottom bar carries the delta: a wedge notched out of its centre.
          Small, because the difference this tool reports is small relative to
          the totals it sits between. */}
      <path
        d="M13 20.1h6a1.7 1.7 0 0 1 0 3.4h-6a1.7 1.7 0 0 1 0-3.4Z"
        fill="#fff"
      />
      <path d="M16 19.4l2.1 3.6h-4.2L16 19.4Z" fill="url(#biet-field)" />
    </svg>
  );
}

/** The mark plus the wordmark, as the header uses it. */
export function Brand() {
  return (
    <div className="brand">
      <BrandMark size={34} />
      <div className="brand-text">
        <span className="brand-eyebrow">Pricing &amp; Market Access</span>
        <span className="brand-name">
          BIET<i>Budget Impact Estimation</i>
        </span>
      </div>
    </div>
  );
}
