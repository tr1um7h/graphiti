'use client';

import { useEffect } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';
import { Canvas } from './canvas';
import { DetailPanel } from './detail-panel';

interface MemoryViewProps {
  groupId: string | undefined;
}

export function MemoryView({ groupId }: MemoryViewProps) {
  const schemaData = useOntologyStore((s) => s.schemaData);
  const loading = useOntologyStore((s) => s.loading);
  const error = useOntologyStore((s) => s.error);
  const setSchemaData = useOntologyStore((s) => s.setSchemaData);
  const setLoading = useOntologyStore((s) => s.setLoading);
  const setError = useOntologyStore((s) => s.setError);
  const setSelectedGroupId = useOntologyStore((s) => s.setSelectedGroupId);
  const fitView = useOntologyStore((s) => s.fitView);

  // Sync group selection to ontology store
  useEffect(() => {
    setSelectedGroupId(groupId ?? null);
  }, [groupId, setSelectedGroupId]);

  // Fetch memory-schema data when group changes
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const url = groupId
      ? `/api/memory-schema?group_id=${encodeURIComponent(groupId)}`
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
  }, [groupId, setSchemaData, setLoading, setError]);

  // Auto-fit view when data loads
  useEffect(() => {
    if (schemaData && !loading) {
      const id = requestAnimationFrame(() => fitView());
      return () => cancelAnimationFrame(id);
    }
  }, [schemaData, loading, fitView]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        加载中...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-destructive">
        {error}
      </div>
    );
  }

  if (!schemaData) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        暂无数据
      </div>
    );
  }

  return (
    <div className="relative flex flex-col flex-1 h-full overflow-hidden">
      <Canvas />
      <DetailPanel />
    </div>
  );
}
