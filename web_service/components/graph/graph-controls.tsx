// components/graph/graph-controls.tsx
'use client';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Maximize, Download, LayoutGrid } from 'lucide-react';
import { useGraphStore } from '@/stores/graph-store';


export function GraphControls() {
  const { layoutAlgorithm, setLayoutAlgorithm } = useGraphStore();

  const handleExportJSON = () => {
    const { graph } = useGraphStore.getState();
    if (!graph) return;
    const data = graph.toJSON();
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'graph-export.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex items-center gap-2">
      <DropdownMenu>
        <DropdownMenuTrigger
          className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
        >
          <LayoutGrid className="h-4 w-4" />
          {layoutAlgorithm === 'forceatlas2' ? 'ForceAtlas2' : 'Circular'}
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => setLayoutAlgorithm('forceatlas2')}>
            ForceAtlas2
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setLayoutAlgorithm('circular')}>
            Circular
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger
          className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
        >
          <Download className="h-4 w-4" />
          导出
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={handleExportJSON}>JSON</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          document.documentElement.requestFullscreen?.();
        }}
      >
        <Maximize className="h-4 w-4" />
      </Button>
    </div>
  );
}
