'use client';

import type { Column as ColumnType } from '@/lib/types';
import { Card } from './card';

export function Column({ column }: { column: ColumnType }) {
  return (
    <div className="w-[220px] flex-shrink-0">
      <div className="text-[10.5px] tracking-[0.12em] text-muted-foreground/60 text-center mb-3.5 font-semibold">
        {column.id.toUpperCase()}
      </div>
      {column.cards.map((card) => (
        <Card key={card.id} card={card} />
      ))}
    </div>
  );
}