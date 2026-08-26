/**
 * The explanation that travels with a field — M21 sections 5.2 and 5.3.
 *
 * Opens on hover **and on keyboard focus**, and carries an accessible name: a
 * tooltip only a mouse can open is not an explanation for everyone.
 *
 * The primary user is a health economics manager, not a modeller. Every entry
 * answers the same four questions in the same order — what it is, in one
 * sentence of plain English; what it changes downstream; what people commonly
 * get wrong; and, for an output, which two worlds it is the difference of.
 */
import { useCallback, useId, useRef, useState, type ReactNode } from "react";

const BUBBLE_WIDTH = 290;
const GAP = 8;
const MARGIN = 12;

export interface HintContent {
  /** One sentence, no jargon, no undefined acronym. */
  what: string;
  /** What moves in the answer when this moves. */
  affects?: string;
  /** The mistake analysts actually make here. */
  watchFor?: string;
}

interface HintProps {
  content: HintContent;
  /** Names the field, so the hint is announced as belonging to it. */
  label: string;
  children?: ReactNode;
}

export function Hint({ content, label, children }: HintProps) {
  const id = useId();
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  /** Positioned against the viewport rather than the trigger's box.
   *
   *  The sidebar scrolls, and an ancestor with `overflow` clips anything
   *  absolutely positioned inside it — which silently truncated this bubble
   *  to the panel width. Fixed positioning escapes every such ancestor, at
   *  the cost of having to place it by hand. It is also flipped to the left
   *  when it would otherwise run off the right edge. */
  const place = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const wouldOverflow = rect.left + BUBBLE_WIDTH + MARGIN > window.innerWidth;
    setAt({
      top: rect.bottom + GAP,
      left: wouldOverflow
        ? Math.max(MARGIN, rect.right - BUBBLE_WIDTH)
        : rect.left,
    });
  }, []);

  const open = at !== null;
  const close = () => setAt(null);

  return (
    <span className="hint-wrap">
      {children}
      <button
        ref={triggerRef}
        type="button"
        className="hint-trigger"
        aria-describedby={open ? id : undefined}
        aria-label={`What is ${label}?`}
        onMouseEnter={place}
        onMouseLeave={close}
        onFocus={place}
        onBlur={close}
        onClick={() => (open ? close() : place())}
      >
        ?
      </button>
      {at && (
        <span
          role="tooltip"
          id={id}
          className="hint-bubble"
          style={{ top: at.top, left: at.left }}
        >
          <span className="hint-what">{content.what}</span>
          {content.affects && (
            <span className="hint-line">
              <b>Changes</b> {content.affects}
            </span>
          )}
          {content.watchFor && (
            <span className="hint-line hint-watch">
              <b>Watch for</b> {content.watchFor}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
