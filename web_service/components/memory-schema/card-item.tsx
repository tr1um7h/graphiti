'use client';

import { useOntologyStore } from '@/stores/ontology-store';
import { cn } from '@/lib/utils';
import type { CardItem as CardItemType } from '@/lib/types';

export function CardItem({ item }: { item: CardItemType }) {
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const relatedItemIds = useOntologyStore((s) => s.relatedItemIds);
  const setFocusedItem = useOntologyStore((s) => s.setFocusedItem);

  const isSelected = focusedItemId === item.id;
  const isRelated = relatedItemIds.has(item.id);

  return (
    <div
      data-itemid={item.id}
      className={cn(
        'px-1.5 py-1 text-xs rounded-md cursor-pointer leading-relaxed',
        'hover:bg-accent/50',
        isSelected && 'outline outline-[1.5px] outline-[#3ecf8e] bg-[rgba(62,207,142,0.08)] text-[#3ecf8e]',
        isRelated && !isSelected && 'text-[#3ecf8e] bg-[rgba(62,207,142,0.05)]'
      )}
      onClick={(e) => {
        e.stopPropagation();
        setFocusedItem(item.id);
      }}
    >
      {item.label}
    </div>
  );
}
