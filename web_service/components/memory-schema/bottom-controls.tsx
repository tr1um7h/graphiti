'use client';

import { useOntologyStore } from '@/stores/ontology-store';

export function BottomControls() {
  const scale = useOntologyStore((s) => s.scale);
  const setScale = useOntologyStore((s) => s.setScale);

  const zoom = (delta: number) => {
    setScale(Math.min(1.6, Math.max(0.5, scale + delta)));
  };

  return (
    <div className="absolute left-7 bottom-6 z-[5] flex items-center gap-2.5">
      <div className="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs text-muted-foreground">
        Transformations
      </div>
      <div className="flex items-center rounded-lg border overflow-hidden">
        <button onClick={() => zoom(-0.1)} className="px-3 py-2 text-sm text-muted-foreground hover:bg-accent border-r">−</button>
        <button onClick={() => zoom(0.1)} className="px-3 py-2 text-sm text-muted-foreground hover:bg-accent border-r">+</button>
        <button onClick={() => setScale(1)} className="px-3 py-2 text-sm text-muted-foreground hover:bg-accent">Fit</button>
      </div>
    </div>
  );
}
