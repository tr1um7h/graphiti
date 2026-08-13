'use client';

import type { Column as ColumnType } from '@/lib/types';
import { Card } from './card';
import { useOntologyStore } from '@/stores/ontology-store';

export function Column({ column }: { column: ColumnType }) {
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const relatedItemIds = useOntologyStore((s) => s.relatedItemIds);

  const visibleCards = focusedItemId
    ? column.cards.filter((card) =>
        card.items.some(
          (item) => focusedItemId === item.id || relatedItemIds.has(item.id)
        )
      )
    : column.cards;

  if (focusedItemId && visibleCards.length === 0) return null;

  return (
    <div className="w-[220px] flex-shrink-0">
      <div className="text-[10.5px] tracking-[0.12em] text-muted-foreground/60 text-center mb-3.5 font-semibold">
        {column.id.toUpperCase()}
      </div>
      {visibleCards.map((card) => (
        <Card key={card.id} card={card} />
      ))}
    </div>
  );
}
