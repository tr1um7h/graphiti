'use client';

import { useOntologyStore } from '@/stores/ontology-store';
import { Column } from './column';
import { EdgeLines } from './edge-lines';
import { BottomControls } from './bottom-controls';

export function Canvas() {
  const schemaData = useOntologyStore((s) => s.schemaData);
  const scale = useOntologyStore((s) => s.scale);
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const clearFocus = useOntologyStore((s) => s.clearFocus);

  if (!schemaData) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        暂无数据
      </div>
    );
  }

  // Find focused item name for display
  const focusName = focusedItemId
    ? findItemLabel(schemaData.columns, focusedItemId)
    : null;

  return (
    <div
      className="relative flex-1 overflow-hidden"
      onClick={(e) => {
        if (e.target === e.currentTarget) clearFocus();
      }}
    >
      {/* Hint / Focus info */}
      {!focusedItemId ? (
        <div className="absolute top-4 left-7 text-sm text-muted-foreground/50 z-[4]">
          Click any item to trace its connections.
        </div>
      ) : (
        <div className="absolute top-4 left-7 text-sm z-[6] flex items-center gap-2.5">
          <span className="text-muted-foreground/50">
            Focused on <b className="font-semibold text-foreground">{focusName}</b>
          </span>
          <span
            className="text-[#3ecf8e] cursor-pointer hover:underline"
            onClick={clearFocus}
          >
            Clear focus
          </span>
        </div>
      )}

      {/* Scalable canvas */}
      <div
        className="absolute inset-0 transition-transform duration-200"
        style={{ transform: `scale(${scale})`, transformOrigin: '50% 0%' }}
        onClick={(e) => {
          const target = e.target as HTMLElement;
          if (!target.closest('[id^="card-"]') && !target.closest('.edge-path') && !target.closest('.bottom-controls')) {
            clearFocus();
          }
        }}
      >
        {/* Only draw edges when focused */}
        {focusedItemId && <EdgeLines />}
        <div className="relative z-[3] flex gap-20 py-10 px-7 h-full">
          {schemaData.columns.map((col) => (
            <Column key={col.id} column={col} />
          ))}
        </div>
      </div>

      <BottomControls />
    </div>
  );
}

function findItemLabel(
  columns: { id: string; cards: { id: string; items: { id: string; label: string }[] }[] }[],
  itemId: string
): string | null {
  for (const col of columns) {
    for (const card of col.cards) {
      for (const item of card.items) {
        if (item.id === itemId) return item.label;
      }
    }
  }
  return null;
}