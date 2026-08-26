/**
 * Publish the sticky header's real height as a CSS variable.
 *
 * Several things have to sit exactly below the header: the input panel sticks
 * to it, the results tab bar sticks under it, and anything scrolled to must
 * clear it. CSS can express "below the header" only as a hard-coded number,
 * and the header does not have one — it wraps from one row to three between a
 * wide monitor and a phone, and it grows again when a result arrives and adds
 * the headline figure to the meta line.
 *
 * A guessed constant is therefore wrong at most widths, and wrong here means
 * content silently hidden under an opaque bar. So it is measured.
 *
 * Measured on every render and on resize rather than through a
 * `ResizeObserver`: those are the only two things that can change this
 * header's height — it has no independently-sized content, no images, no
 * embedded text that reflows on its own — and a layout effect after render is
 * both simpler and portable to environments where `ResizeObserver` does not
 * deliver (some headless browsers among them, which is how this was found).
 */

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

const VARIABLE = "--topbar-h";

export function useStickyHeaderHeight(ref: React.RefObject<HTMLElement>): void {
  const published = useRef<number>(0);

  const publish = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    // Rounded up: half a pixel short leaves a hairline of content above the
    // bar, which reads as a rendering fault rather than a deliberate edge.
    const height = Math.ceil(element.getBoundingClientRect().height);
    // Writing the same value back would invalidate layout on every render for
    // no change, and this runs after each one.
    if (height === published.current || height <= 0) return;
    published.current = height;
    document.documentElement.style.setProperty(VARIABLE, `${height}px`);
  }, [ref]);

  // No dependency array: the header's height is a function of what was just
  // rendered, so it is remeasured whenever anything renders.
  useLayoutEffect(publish);

  useEffect(() => {
    window.addEventListener("resize", publish);
    return () => window.removeEventListener("resize", publish);
  }, [publish]);
}
