'use client';

import { useOntologyStore } from '@/stores/ontology-store';
import { ArrowLeft, X } from 'lucide-react';
import type { Connection, NodeDetail } from '@/lib/types';

export function DetailPanel() {
  const schemaData = useOntologyStore((s) => s.schemaData);
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const clearFocus = useOntologyStore((s) => s.clearFocus);
  const setFocusedItem = useOntologyStore((s) => s.setFocusedItem);

  const isOpen = !!focusedItemId;

  if (!schemaData) return null;

  // Find the focused item's label and detail
  const { label, detail } = findItemDetail(schemaData.columns, schemaData.details, focusedItemId);

  return (
    <div
      className={`absolute top-0 right-0 h-full w-[340px] bg-card border-l z-[8] transform transition-transform duration-300 overflow-y-auto ${
        isOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 pt-5 pb-4">
        <div
          className="flex items-center gap-1 text-sm text-muted-foreground cursor-pointer hover:text-foreground"
          onClick={() => {
            const parentId =
              detail?.parent_id ||
              (detail?.parent ? findItemIdByLabel(schemaData.columns, detail.parent) : null);
            if (parentId) setFocusedItem(parentId);
          }}
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>{detail?.parent || ''}</span>
        </div>
        <button
          onClick={clearFocus}
          className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Title */}
      <h2 className="text-2xl font-semibold tracking-tight px-5 mb-1">{label}</h2>
      <p className="text-sm text-muted-foreground px-5 mb-6">{detail?.type || ''}</p>

      {/* Connections */}
      <div className="px-5">
        <div className="text-[10.5px] tracking-[0.12em] text-muted-foreground/60 font-semibold mb-3">
          CONNECTIONS
        </div>
        {renderConnections(detail?.connections || [], schemaData, setFocusedItem)}
      </div>
    </div>
  );
}

function findItemDetail(
  columns: { id: string; cards: { id: string; items: { id: string; label: string }[] }[] }[],
  details: Record<string, NodeDetail>,
  itemId: string | null
): { label: string; detail: NodeDetail | null } {
  if (!itemId) return { label: '', detail: null };

  for (const col of columns) {
    for (const card of col.cards) {
      for (const item of card.items) {
        if (item.id === itemId) {
          return {
            label: item.label,
            detail: details[itemId] || null,
          };
        }
      }
    }
  }
  return { label: itemId, detail: null };
}

function renderConnections(
  connections: Connection[],
  schemaData: { columns: { cards: { items: { id: string; label: string }[] }[] }[] },
  setFocusedItem: (id: string | null) => void
) {
  if (connections.length === 0) {
    return (
      <div className="text-sm text-muted-foreground text-center py-4">No connections found</div>
    );
  }

  return connections.map((conn, idx) => (
    <div key={idx}>
      {conn.dir === 'forward' && (
        <div className="flex items-center justify-center my-2.5 text-muted-foreground/50 text-sm">→</div>
      )}
      {conn.dir === 'backward' && (
        <div className="flex items-center justify-center my-2.5 text-muted-foreground/50 text-sm">←</div>
      )}
      {conn.kind === 'tag' && (
        <div
          className="flex items-center justify-center bg-muted border rounded-lg px-3.5 py-2 text-sm mb-0.5 cursor-pointer hover:border-[#3ecf8e] hover:text-[#3ecf8e]"
          onClick={() => {
            const itemId =
              conn.target_id || findItemIdByLabel(schemaData.columns, conn.text);
            if (itemId) setFocusedItem(itemId);
          }}
        >
          {conn.text}
        </div>
      )}
      {conn.kind === 'quote' && (
        <div className="bg-muted border rounded-lg px-3.5 py-3 text-[12.5px] leading-relaxed text-muted-foreground mb-2.5">
          {conn.text}
        </div>
      )}
    </div>
  ));
}

function findItemIdByLabel(
  columns: { cards: { items: { id: string; label: string }[] }[] }[],
  label: string
): string | null {
  for (const col of columns) {
    for (const card of col.cards) {
      for (const item of card.items) {
        if (item.label === label) return item.id;
      }
    }
  }
  return null;
}
