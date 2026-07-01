'use client';

import { Button } from '@/components/ui/button';

interface RingControlProps {
  depth: 1 | 2;
  onChange: (depth: 1 | 2) => void;
}

export default function RingControl({ depth, onChange }: RingControlProps) {
  return (
    <div className="flex items-center gap-1 rounded-lg border bg-muted/50 p-1">
      <Button
        variant={depth === 1 ? 'default' : 'ghost'}
        size="xs"
        onClick={() => onChange(1)}
      >
        1环
      </Button>
      <Button
        variant={depth === 2 ? 'default' : 'ghost'}
        size="xs"
        onClick={() => onChange(2)}
      >
        2环
      </Button>
    </div>
  );
}
