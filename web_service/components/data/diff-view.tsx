'use client';

import { useCallback, useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface DiffViewProps {
  left: string;
  right: string;
}

interface TableDiff {
  added: number;
  removed: number;
  modified: number;
  conflicts: number;
}

interface DiffResult {
  version: number;
  metadata: {
    from_group_id: string;
    to_group_id: string;
    created_at: string;
  };
  changes: Record<string, TableDiff>;
}

export function DiffView({ left, right }: DiffViewProps) {
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDiff = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ left, right });
    try {
      const res = await fetch(`/api/data/diff?${params}`, { cache: 'no-store' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Diff failed' }));
        throw new Error(err.error || err.detail || 'Diff failed');
      }
      const data = await res.json();
      setDiff(data);
    } catch (err) {
      console.error('Diff failed:', err);
      setError(err instanceof Error ? err.message : 'Diff failed');
    } finally {
      setLoading(false);
    }
  }, [left, right]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadDiff(); }, [loadDiff]);

  const handleExport = async () => {
    try {
      const params = new URLSearchParams({ left, right });
      const res = await fetch(`/api/data/diff/export?${params}`);
      if (!res.ok) throw new Error('Export failed');

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `diff_${left}_vs_${right}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Export failed:', err);
      alert('Export failed');
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        Computing diff...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-destructive/10 p-8 text-center">
        <p className="text-destructive font-medium">Error: {error}</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={loadDiff}>
          Retry
        </Button>
      </div>
    );
  }

  if (!diff) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        No diff data
      </div>
    );
  }

  const tables = Object.keys(diff.changes);
  const totals = tables.reduce(
    (acc, table) => {
      const t = diff.changes[table];
      acc.added += t.added;
      acc.removed += t.removed;
      acc.modified += t.modified;
      acc.conflicts += t.conflicts;
      return acc;
    },
    { added: 0, removed: 0, modified: 0, conflicts: 0 }
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-semibold">
          Diff: {left} ↔ {right}
        </h3>
        <Button variant="outline" size="sm" onClick={handleExport}>
          <Download className="h-4 w-4 mr-2" />
          Export Diff
        </Button>
      </div>

      <div className="rounded-lg border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-sm font-medium">
                  Table
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium text-green-600">
                  Added
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium text-red-600">
                  Removed
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium text-blue-600">
                  Modified
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium text-orange-600">
                  Conflicts
                </th>
              </tr>
            </thead>
            <tbody>
              {tables.map((tableName) => {
                const t = diff.changes[tableName];
                return (
                  <tr
                    key={tableName}
                    className="border-b last:border-0 hover:bg-muted/30"
                  >
                    <td className="px-4 py-3 font-medium">{tableName}</td>
                    <td className="px-4 py-3 text-right text-sm">
                      {t.added > 0 && (
                        <span className="text-green-600">+{t.added}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-sm">
                      {t.removed > 0 && (
                        <span className="text-red-600">-{t.removed}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-sm">
                      {t.modified > 0 && (
                        <span className="text-blue-600">~{t.modified}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-sm">
                      {t.conflicts > 0 && (
                        <span className="text-orange-600">!{t.conflicts}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              <tr className="bg-muted/50 font-semibold">
                <td className="px-4 py-3">Total</td>
                <td className="px-4 py-3 text-right text-sm text-green-600">
                  +{totals.added}
                </td>
                <td className="px-4 py-3 text-right text-sm text-red-600">
                  -{totals.removed}
                </td>
                <td className="px-4 py-3 text-right text-sm text-blue-600">
                  ~{totals.modified}
                </td>
                <td className="px-4 py-3 text-right text-sm text-orange-600">
                  {totals.conflicts > 0 && `!${totals.conflicts}`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}