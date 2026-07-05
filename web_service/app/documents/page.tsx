'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DocumentTable } from '@/components/documents/document-table';
import { UploadDialog } from '@/components/layout/upload-dialog';
import type { Document, DocumentStatus } from '@/lib/types';

// The backend commits an uploaded document asynchronously (queue_service processes
// the episode a few seconds after the upload response). Polling bridges that gap.
const POLL_INTERVAL_MS = 2000;
// 120s is generous: a single small doc commits in ~5s, but larger docs (LLM
// entity extraction) can take much longer. The old 60s window was too tight.
const POLL_TIMEOUT_MS = 120_000;

interface GroupOption {
  id: string;
  name: string;
  count: number;
}

function inferDocType(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.pdf')) return 'PDF';
  if (lower.endsWith('.docx')) return 'DOCX';
  if (lower.endsWith('.md')) return 'MD';
  if (lower.startsWith('http')) return 'URL';
  return 'TXT';
}

function isPlaceholder(doc: Document): boolean {
  return doc.id.startsWith('pending-');
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [groups, setGroups] = useState<GroupOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | 'all'>('all');
  const [groupId, setGroupId] = useState('all');
  const [uploadOpen, setUploadOpen] = useState(false);

  // Refs hold the polling task out of React's render/effect lifecycle so that
  // opening/closing the dialog or re-rendering does NOT cancel an in-flight
  // upload's polling. Only unmount stops it.
  const mountedRef = useRef(true);
  const pollingNamesRef = useRef<Set<string>>(new Set());
  // Ids of documents being/just deleted — excluded from poll refreshes so a
  // delete racing with another upload's polling can't resurrect a deleted doc.
  const deletedIdsRef = useRef<Set<string>>(new Set());
  // Monotonic counter so two uploads of the same filename get unique ids.
  const placeholderSeqRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchGroups = useCallback(async (): Promise<GroupOption[]> => {
    try {
      const res = await fetch('/api/graph/groups', { cache: 'no-store' });
      if (!res.ok) return [];
      return (await res.json()) as GroupOption[];
    } catch {
      return [];
    }
  }, []);

  const fetchDocuments = useCallback(async (): Promise<Document[]> => {
    const res = await fetch('/api/documents', { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch');
    return (await res.json()) as Document[];
  }, []);

  // Initial load
  useEffect(() => {
    Promise.all([fetchDocuments(), fetchGroups()])
      .then(([docs, grps]) => {
        setDocuments(docs);
        setGroups(grps);
      })
      .catch((err) => console.error('Failed to fetch documents:', err))
      .finally(() => setLoading(false));
  }, [fetchDocuments, fetchGroups]);

  // Poll the list until the uploaded document transitions from pending to completed.
  // The backend /queue/status endpoint now provides real pending state, so
  // polling just refreshes the list until the doc shows as 'completed'.
  const pollForDocument = useCallback(
    async (name: string) => {
      if (pollingNamesRef.current.has(name)) return;
      pollingNamesRef.current.add(name);

      const deadline = Date.now() + POLL_TIMEOUT_MS;

      while (mountedRef.current && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (!mountedRef.current) break;

        try {
          const fetched = await fetchDocuments();
          setDocuments(fetched.filter((f) => !deletedIdsRef.current.has(f.id)));
          fetchGroups().then(setGroups).catch(() => {});

          // Done when the doc exists AND is no longer pending/processing
          const doc = fetched.find((d) => d.name === name);
          if (doc && doc.status !== 'pending' && doc.status !== 'processing') {
            pollingNamesRef.current.delete(name);
            return;
          }
        } catch (err) {
          console.error('Poll fetch failed:', err);
        }
      }

      if (!mountedRef.current) return;
      pollingNamesRef.current.delete(name);
      // Mark as failed if still pending after timeout
      setDocuments((prev) =>
        prev.map((d) =>
          d.name === name && (d.status === 'pending' || d.status === 'processing')
            ? { ...d, status: 'failed' as DocumentStatus }
            : d,
        ),
      );
    },
    [fetchDocuments, fetchGroups],
  );

  // Called by UploadDialog the moment an upload request succeeds.
  const handleUploaded = useCallback(
    (name: string, gid: string) => {
      // Refresh immediately — backend /queue/status now returns the pending job
      fetchDocuments().then((fetched) => {
        setDocuments(fetched.filter((f) => !deletedIdsRef.current.has(f.id)));
      });
      // Auto-switch filter so the uploaded doc is visible
      if (groupId !== 'all' && groupId !== gid) {
        setGroupId('all');
      }
      void pollForDocument(name);
    },
    [pollForDocument, groupId, fetchDocuments],
  );

  // Delete a document. Completed docs are removed from the graph; failed
  // placeholders (timed-out uploads) are just dropped locally. In-flight
  // (processing/pending) rows are not deletable — the table disables them.
  const handleDelete = useCallback(async (doc: Document) => {
    if (isPlaceholder(doc)) {
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
      return;
    }

    const confirmed = window.confirm(
      `Delete "${doc.name}"?\n\nThis removes the document and its extracted entities from the knowledge graph. This action cannot be undone.`,
    );
    if (!confirmed) return;

    // Optimistic: suppress + remove now; roll back if the backend rejects it.
    deletedIdsRef.current.add(doc.id);
    setDocuments((prev) => prev.filter((d) => d.id !== doc.id));

    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(doc.id)}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Delete failed' }));
        throw new Error(err.error || 'Delete failed');
      }
    } catch (error) {
      console.error('Failed to delete document:', error);
      deletedIdsRef.current.delete(doc.id);
      setDocuments((prev) => (prev.some((d) => d.id === doc.id) ? prev : [...prev, doc]));
      window.alert(
        `Failed to delete "${doc.name}": ${error instanceof Error ? error.message : 'Unknown error'}`,
      );
    }
  }, []);

  const filteredDocuments = documents.filter((doc) => {
    if (statusFilter !== 'all' && doc.status !== statusFilter) return false;
    if (groupId !== 'all' && doc.group_id !== groupId) return false;
    if (search && !doc.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Document Management</h2>
          <p className="text-sm text-muted-foreground">
            {documents.length} documents total
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" />
            Upload
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={groupId}
          onChange={(e) => setGroupId(e.target.value)}
          className="h-8 rounded-md border bg-background px-3 text-sm"
        >
          <option value="all">All Groups</option>
          <option value="default">default</option>
          {groups.map((g) => (
            <option key={g.id || g.name} value={g.id || g.name}>
              {g.id || g.name} ({g.count})
            </option>
          ))}
        </select>

        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-8"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as DocumentStatus | 'all')}
          className="h-8 rounded-md border bg-background px-3 text-sm"
        >
          <option value="all">All Status</option>
          <option value="completed">✅ 已处理</option>
          <option value="processing">🔄 处理中</option>
          <option value="pending">⏳ 排队中</option>
          <option value="failed">❌ 失败</option>
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          Loading documents...
        </div>
      ) : (
        <DocumentTable documents={filteredDocuments} onDelete={handleDelete} />
      )}

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        groups={groups}
        onUploaded={handleUploaded}
      />
    </div>
  );
}
