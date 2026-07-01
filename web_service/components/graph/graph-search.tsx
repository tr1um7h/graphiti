// components/graph/graph-search.tsx
'use client';

import { useState, useRef, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';

interface SearchResult {
  id: string;
  name: string;
  type: string;
}

interface GraphSearchProps {
  groupId?: string;
  onSelect: (nodeId: string) => void;
}

export function GraphSearch({ groupId, onSelect }: GraphSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        let url = `/api/graph/search?q=${encodeURIComponent(query)}`;
        if (groupId) {
          url += `&group_id=${encodeURIComponent(groupId)}`;
        }
        const res = await fetch(url);
        const data = await res.json();
        setResults(data);
        setOpen(true);
      } catch {
        setResults([]);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, groupId]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="搜索实体..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-64 pl-9"
        />
      </div>

      {open && results.length > 0 && (
        <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-md border bg-background shadow-lg">
          {results.map((r) => (
            <button
              key={r.id}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent"
              onClick={() => {
                onSelect(r.id);
                setOpen(false);
                setQuery('');
              }}
            >
              <span className="font-medium">{r.name}</span>
              <span className="text-xs text-muted-foreground">{r.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
