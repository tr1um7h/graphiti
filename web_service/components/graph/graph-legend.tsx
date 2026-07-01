// components/graph/graph-legend.tsx
'use client';

import { NODE_COLORS } from '@/lib/graph-theme';
import { useGraphStore } from '@/stores/graph-store';

export function GraphLegend() {
  const { hiddenTypes, toggleType, nodeCount, edgeCount } = useGraphStore();

  return (
    <div className="flex items-center gap-4 border-t bg-background/95 px-4 py-2 text-sm backdrop-blur">
      <div className="flex items-center gap-3">
        {Object.entries(NODE_COLORS)
          .filter(([key]) => key !== 'default')
          .map(([type, color]) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
              className={`flex items-center gap-1.5 transition-opacity ${
                hiddenTypes.has(type) ? 'opacity-30' : 'opacity-100'
              }`}
            >
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-muted-foreground">{type}</span>
            </button>
          ))}
      </div>
      <div className="ml-auto text-xs text-muted-foreground">
        节点: {nodeCount} | 边: {edgeCount}
      </div>
    </div>
  );
}
