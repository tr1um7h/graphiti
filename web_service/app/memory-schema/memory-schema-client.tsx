'use client';

import { useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useOntologyStore } from '@/stores/ontology-store';
import { OntologySelector } from '@/components/memory-schema/ontology-selector';
import { Canvas } from '@/components/memory-schema/canvas';
import { DetailPanel } from '@/components/memory-schema/detail-panel';
import { RefreshCw } from 'lucide-react';

export default function MemorySchemaClient() {
  const {
    schemaData,
    loading,
    error,
    groups,
    selectedGroupId,
    setSchemaData,
    setLoading,
    setError,
    setGroups,
    setSelectedGroupId,
  } = useOntologyStore(
    useShallow((s) => ({
      schemaData: s.schemaData,
      loading: s.loading,
      error: s.error,
      groups: s.groups,
      selectedGroupId: s.selectedGroupId,
      setSchemaData: s.setSchemaData,
      setLoading: s.setLoading,
      setError: s.setError,
      setGroups: s.setGroups,
      setSelectedGroupId: s.setSelectedGroupId,
    }))
  );

  // Fetch groups on mount and auto-select first group
  useEffect(() => {
    fetch('/api/graph/groups')
      .then((res) => (res.ok ? res.json() : []))
      .then((data: { id: string; name: string; episode_count: number; entity_count: number }[]) => {
        setGroups(data);
        // Auto-select first group if none selected and groups exist
        if (!selectedGroupId && data.length > 0) {
          setSelectedGroupId(data[0].id);
        }
      })
      .catch((err) => console.error('Failed to load groups:', err));
  }, [setGroups, setSelectedGroupId, selectedGroupId]);

  // Fetch memory-schema data when group selection changes
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const url = selectedGroupId
      ? `/api/memory-schema?group_id=${encodeURIComponent(selectedGroupId)}`
      : '/api/memory-schema';

    fetch(url)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) setSchemaData(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedGroupId, setSchemaData, setLoading, setError]);

  const displayName = selectedGroupId ?? 'All Groups';
  if (loading) return <div className="flex flex-1 items-center justify-center text-muted-foreground">加载中...</div>;
  if (error) return <div className="flex flex-1 items-center justify-center text-destructive">{error}</div>;

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Header */}
      <header className="flex items-start justify-between px-7 pt-5 pb-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Memory Schema</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Define extraction rules and re-process to rebuild the memory for{' '}
            <b className="font-medium text-foreground">{displayName}</b>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
            <span className="h-2 w-2 rounded-full bg-[#38d0e0]" />
            {displayName}
          </div>
          <button className="rounded-lg border p-2 hover:bg-accent" title="Refresh">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* Toolbar */}
      <div className="flex items-center justify-end px-7 pb-4">
        <OntologySelector />
      </div>

      {/* Canvas */}
      <Canvas />

      {/* Detail Panel */}
      <DetailPanel />
    </div>
  );
}
