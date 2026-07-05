'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, Upload, FileDown, GitCompare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GroupsTable } from '@/components/data/groups-table';
import { GroupDetail } from '@/components/data/group-detail';
import { DiffView } from '@/components/data/diff-view';
import { ImportDataDialog } from '@/components/data/import-data-dialog';
import { ImportPatchDialog } from '@/components/data/import-patch-dialog';
import type { GroupStats } from '@/lib/types';

type Mode = 'list' | 'single' | 'diff';

export default function DataPageClient() {
  const [groups, setGroups] = useState<GroupStats[]>([]);
  const [selectedGroup1, setSelectedGroup1] = useState<string | null>(null);
  const [selectedGroup2, setSelectedGroup2] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [importDataOpen, setImportDataOpen] = useState(false);
  const [importPatchOpen, setImportPatchOpen] = useState(false);

  // Derive mode from selection state
  const mode: Mode = useMemo(() => {
    if (!selectedGroup1) return 'list';
    if (!selectedGroup2) return 'single';
    return 'diff';
  }, [selectedGroup1, selectedGroup2]);

  const fetchGroups = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/data/groups', { cache: 'no-store' });
      if (!res.ok) throw new Error('Failed to fetch groups');
      const data = await res.json();
      setGroups(data);
    } catch (error) {
      console.error('Failed to fetch groups:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchGroups(); }, [fetchGroups]);

  const handleRefresh = useCallback(() => {
    fetchGroups();
  }, [fetchGroups]);

  const handleSelectGroup = (groupId: string) => {
    if (!selectedGroup1) {
      setSelectedGroup1(groupId);
    } else if (selectedGroup1 !== groupId) {
      setSelectedGroup2(groupId);
    }
  };

  const handleClearSelection = () => {
    setSelectedGroup1(null);
    setSelectedGroup2(null);
  };

  const handleDelete = async (groupId: string) => {
    if (!confirm(`Delete group "${groupId}"? This cannot be undone.`)) return;
    setDeleting(groupId);
    try {
      const res = await fetch(`/api/data/groups/${encodeURIComponent(groupId)}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Delete failed' }));
        throw new Error(err.error || err.detail || 'Delete failed');
      }
      // Clear selection if the deleted group was selected
      if (selectedGroup1 === groupId) setSelectedGroup1(null);
      if (selectedGroup2 === groupId) setSelectedGroup2(null);
      fetchGroups();
    } catch (error) {
      console.error('Delete failed:', error);
      alert(error instanceof Error ? error.message : 'Delete failed');
    } finally {
      setDeleting(null);
    }
  };

  const handleImported = () => {
    fetchGroups();
    setImportDataOpen(false);
  };

  const handlePatchApplied = () => {
    fetchGroups();
    setImportPatchOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Data Management</h2>
          <p className="text-sm text-muted-foreground">
            {groups.length} groups total
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setImportDataOpen(true)}
          >
            <Upload className="h-4 w-4" />
            Import Data
          </Button>
          {selectedGroup1 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setImportPatchOpen(true)}
            >
              <FileDown className="h-4 w-4" />
              Import Patch
            </Button>
          )}
        </div>
      </div>

      {/* Group Selector */}
      <div className="flex items-center gap-4">
        <select
          value={selectedGroup1 || ''}
          onChange={(e) => setSelectedGroup1(e.target.value || null)}
          className="h-9 rounded-md border bg-background px-3 text-sm"
        >
          <option value="">Select source group...</option>
          {groups.map((g) => (
            <option key={g.group_id} value={g.group_id}>
              {g.group_id}
            </option>
          ))}
        </select>

        {selectedGroup1 && (
          <>
            <GitCompare className="h-4 w-4 text-muted-foreground" />
            <select
              value={selectedGroup2 || ''}
              onChange={(e) => setSelectedGroup2(e.target.value || null)}
              className="h-9 rounded-md border bg-background px-3 text-sm"
            >
              <option value="">Select target group (optional)...</option>
              {groups
                .filter((g) => g.group_id !== selectedGroup1)
                .map((g) => (
                  <option key={g.group_id} value={g.group_id}>
                    {g.group_id}
                  </option>
                ))}
            </select>
          </>
        )}

        {(selectedGroup1 || selectedGroup2) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearSelection}
            className="text-muted-foreground"
          >
            Clear
          </Button>
        )}
      </div>

      {/* Content based on mode */}
      {loading ? (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          Loading groups...
        </div>
      ) : mode === 'list' ? (
        <GroupsTable groups={groups} onSelect={handleSelectGroup} onDelete={handleDelete} deleting={deleting} />
      ) : mode === 'single' ? (
        <GroupDetail groupId={selectedGroup1!} />
      ) : (
        <DiffView left={selectedGroup1!} right={selectedGroup2!} />
      )}

      <ImportDataDialog
        open={importDataOpen}
        onOpenChange={setImportDataOpen}
        onImported={handleImported}
      />

      <ImportPatchDialog
        open={importPatchOpen}
        onOpenChange={setImportPatchOpen}
        targetGroupId={selectedGroup1 || ''}
        groups={groups}
        onApplied={handlePatchApplied}
      />
    </div>
  );
}
