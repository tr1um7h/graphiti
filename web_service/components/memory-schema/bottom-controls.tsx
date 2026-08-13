'use client';

import { useOntologyStore } from '@/stores/ontology-store';

export function BottomControls() {
  const zoomBy = useOntologyStore((s) => s.zoomBy);
  const fitView = useOntologyStore((s) => s.fitView);

  return (
    <div className="bottom-controls absolute left-7 bottom-6 z-[5] flex items-center gap-2.5">
      <div className="flex items-center rounded-lg border overflow-hidden">
        <button onClick={() => zoomBy(-0.1)} className="px-3 py-2 text-sm text-muted-foreground hover:bg-accent border-r">−</button>
        <button onClick={() => zoomBy(0.1)} className="px-3 py-2 text-sm text-muted-foreground hover:bg-accent border-r">+</button>
        <button onClick={fitView} className="px-3 py-2 text-sm text-muted-foreground hover:bg-accent">Fit</button>
      </div>
    </div>
  );
}
