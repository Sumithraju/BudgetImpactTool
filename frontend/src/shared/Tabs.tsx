/**
 * A tab strip and its panels.
 *
 * Lives in `shared/` rather than a slice because more than one area needs it
 * and a slice may not import another slice's internals.
 *
 * Keyboard behaviour follows the WAI-ARIA tabs pattern: arrow keys move
 * between tabs, Home and End jump to the ends, and only the active tab is in
 * the tab order — so a keyboard user reaches the panel in two keystrokes
 * rather than stepping through every tab first.
 */
import { useCallback, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabDefinition {
  id: string;
  label: string;
  /** Rendered beside the label — a count, or a state marker. */
  badge?: string | number;
  content: ReactNode;
}

interface TabsProps {
  tabs: TabDefinition[];
  activeId: string;
  onChange: (id: string) => void;
}

export function Tabs({ tabs, activeId, onChange }: TabsProps) {
  const base = useId();
  const stripRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const index = tabs.findIndex((t) => t.id === activeId);
      if (index < 0) return;

      const moves: Record<string, number> = {
        ArrowRight: index + 1,
        ArrowLeft: index - 1,
        Home: 0,
        End: tabs.length - 1,
      };
      const target = moves[event.key];
      if (target === undefined) return;

      event.preventDefault();
      const next = tabs[(target + tabs.length) % tabs.length];
      onChange(next.id);
      // Focus follows selection, which is what the pattern expects when the
      // panel is revealed immediately rather than on activation.
      stripRef.current
        ?.querySelector<HTMLButtonElement>(`#${CSS.escape(`${base}-tab-${next.id}`)}`)
        ?.focus();
    },
    [activeId, base, onChange, tabs],
  );

  const active = tabs.find((t) => t.id === activeId) ?? tabs[0];

  return (
    <div className="tabs">
      <div className="tabstrip" role="tablist" ref={stripRef} onKeyDown={handleKeyDown}>
        {tabs.map((tab) => {
          const selected = tab.id === active?.id;
          return (
            <button
              key={tab.id}
              id={`${base}-tab-${tab.id}`}
              type="button"
              role="tab"
              className={selected ? "tab tab-active" : "tab"}
              aria-selected={selected}
              aria-controls={`${base}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
            >
              {tab.label}
              {tab.badge !== undefined && <span className="tab-badge">{tab.badge}</span>}
            </button>
          );
        })}
      </div>

      {active && (
        <div
          id={`${base}-panel-${active.id}`}
          role="tabpanel"
          aria-labelledby={`${base}-tab-${active.id}`}
          className="tabpanel"
          tabIndex={0}
        >
          {active.content}
        </div>
      )}
    </div>
  );
}
