'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';

interface SearchResult {
  id: string;
  name: string;
  type: string;
}

interface EntitySelectorProps {
  onSelect: (id: string, name: string, type: string) => void;
  placeholder?: string;
}

export default function EntitySelector({
  onSelect,
  placeholder = '搜索实体...',
}: EntitySelectorProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/graph/search?q=${encodeURIComponent(q)}`);
      const data: SearchResult[] = await res.json();
      setResults(data);
      setOpen(data.length > 0);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInput = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const handleSelect = (item: SearchResult) => {
    setQuery(item.name);
    setOpen(false);
    onSelect(item.id, item.name, item.type);
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative w-64">
      <div className="relative">
        <Search className="absolute left-2 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setOpen(true);
          }}
          placeholder={placeholder}
          className="pl-8"
        />
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md">
          <ul className="max-h-60 overflow-auto py-1 text-sm">
            {loading && (
              <li className="px-3 py-2 text-muted-foreground">搜索中...</li>
            )}
            {!loading && results.length === 0 && (
              <li className="px-3 py-2 text-muted-foreground">无结果</li>
            )}
            {results.map((item) => (
              <li
                key={item.id}
                className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-accent"
                onClick={() => handleSelect(item)}
              >
                <span className="font-medium">{item.name}</span>
                <span className="text-xs text-muted-foreground">{item.type}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
