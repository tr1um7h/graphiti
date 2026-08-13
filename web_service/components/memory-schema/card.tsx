'use client';

import { useState } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';
import { cn } from '@/lib/utils';
import type { Card as CardType } from '@/lib/types';
import { CardItem } from './card-item';

const MAX_VISIBLE = 5;
const EXPAND_STEP = 5;

export function Card({ card }: { card: CardType }) {
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const relatedItemIds = useOntologyStore((s) => s.relatedItemIds);
  const [expandedCount, setExpandedCount] = useState(MAX_VISIBLE);

  const visibleItems = focusedItemId
    ? card.items.filter((item) => focusedItemId === item.id || relatedItemIds.has(item.id))
    : card.items;

  const displayItems = focusedItemId ? visibleItems : visibleItems.slice(0, expandedCount);
  const hasMore = !focusedItemId && visibleItems.length > expandedCount;

  const isHidden = focusedItemId && visibleItems.length === 0;

  const handleExpand = () => {
    setExpandedCount((prev) => prev + EXPAND_STEP);
  };

  return (
   <div
     id={`card-${card.id}`}
     data-memory-card
      data-card-color={card.color}
     className={cn(
       'rounded-lg border bg-card p-2.5 mb-6 transition-opacity duration-250',
       isHidden && 'hidden'
     )}
   >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="h-[7px] w-[7px] rounded-full flex-shrink-0"
          style={{ backgroundColor: card.color }}
        />
        <span className="text-[10.5px] tracking-wider text-muted-foreground font-semibold flex-1 truncate">
          {card.title}
        </span>
        <span className="text-[10px] text-muted-foreground/60 bg-muted rounded-lg px-1.5 py-0.5">
          {visibleItems.length}
        </span>
      </div>

      <div>
        {displayItems.map((item) => (
          <CardItem key={item.id} item={item} />
        ))}
        {hasMore && (
          <div
            className="px-1.5 py-1 text-xs text-muted-foreground/60 cursor-pointer hover:text-accent-foreground hover:bg-accent/50 rounded-md"
            onClick={handleExpand}
          >
            + {visibleItems.length - expandedCount} more
          </div>
        )}
      </div>
    </div>
  );
}
