'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Check,
  ChevronRight,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Send,
  Settings2,
  Trash2,
  Type,
  Upload,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { NodeEditDialog } from '@/components/ingest/node-edit-dialog';
import { EdgeEditDialog } from '@/components/ingest/edge-edit-dialog';
import { useGroupStore } from '@/stores/group-store';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EpisodePreview {
  uuid: string;
  name: string;
  content: string;
  group_id: string;
  source: string;
  source_description: string;
}

interface NodePreview {
  uuid: string;
  name: string;
  labels: string[];
  summary: string;
  group_id: string;
  is_new: boolean;
}

interface EdgePreview {
  uuid: string;
  name: string;
  fact: string;
  source_node_uuid: string;
  source_node_name: string;
  target_node_uuid: string;
  target_node_name: string;
  valid_at: string | null;
  invalid_at: string | null;
  expired_at: string | null;
}

interface PreviewMemoryResponse {
  episode: EpisodePreview;
  nodes: NodePreview[];
  edges: EdgePreview[];
  invalidated_edges: EdgePreview[];
}

type IngestStep = 'input' | 'processing' | 'review';
type InputMode = 'text' | 'file';
type IngestMode = 'preview' | 'direct';

interface GroupOption {
  id: string;
  name: string;
  count: number;
}

interface SchemaOption {
  id: number;
  name: string;
  description: string;
  entity_type_count: number;
  edge_type_count: number;
}

interface SchemaDetail {
  id: number;
  name: string;
  description: string;
  entity_types: { name: string; description: string; attributes?: { name: string; type: string; description?: string }[] }[];
  edge_types: { name: string; description: string; attributes?: { name: string; type: string; description?: string }[] }[];
  custom_instructions: string;
}

// ---------------------------------------------------------------------------
// Stage definitions
// ---------------------------------------------------------------------------

const STAGES = [
  { key: 'retrieving_context', label: '检索上下文' },
  { key: 'extracting_entities', label: '提取实体' },
  { key: 'resolving_entities', label: '解析实体（去重/合并）' },
  { key: 'extracting_edges', label: '提取关系' },
  { key: 'resolving_edges', label: '解析关系（去重/矛盾检测）' },
  { key: 'extracting_attributes', label: '提取属性摘要' },
];

// ---------------------------------------------------------------------------
// UUID 生成：crypto.randomUUID() 仅在安全上下文（HTTPS / localhost）可用，
// 内网 HTTP 环境需要 Math.random 回退
// ---------------------------------------------------------------------------
function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // RFC 4122 v4 UUID via Math.random
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function IngestPage() {
  const router = useRouter();

  // Groups
  const [groups, setGroups] = useState<GroupOption[]>([]);
  const storedGroupId = useGroupStore((s) => s.selectedGroupId);
  const setStoredGroup = useGroupStore((s) => s.setSelectedGroup);

  // Step 1 state
  const [step, setStep] = useState<IngestStep>('input');
  const [content, setContent] = useState('');
  const [name, setName] = useState('');
  const [groupId, setGroupId] = useState('');
  const [source, setSource] = useState('text');
  const [inputMode, setInputMode] = useState<InputMode>('text');
  const [mode, setMode] = useState<IngestMode>('preview');
  const [customGroup, setCustomGroup] = useState('');
  const [showCustomGroup, setShowCustomGroup] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [fileName, setFileName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Schema selection
  const [schemas, setSchemas] = useState<SchemaOption[]>([]);
  const [schemaId, setSchemaId] = useState<number | null>(null);
  const [schemaDetail, setSchemaDetail] = useState<SchemaDetail | null>(null);

  // Processing state
  const [stage, setStage] = useState('');
  const [pollError, setPollError] = useState<string | null>(null);
  const cancelRef = useRef(false);
  const submittingRef = useRef(false);
  const taskIdRef = useRef<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const POLL_MAX_CONSECUTIVE_ERRORS = 5;

  // Preview result state
  const [preview, setPreview] = useState<PreviewMemoryResponse | null>(null);
  const [excludedNodeIds, setExcludedNodeIds] = useState<Set<string>>(new Set());
  const [excludedEdgeIds, setExcludedEdgeIds] = useState<Set<string>>(new Set());

  // Edit dialog state
  const [editingNode, setEditingNode] = useState<{
    node: NodePreview;
    isNew: boolean;
  } | null>(null);
  const [editingEdge, setEditingEdge] = useState<{
    edge: EdgePreview;
    isNew: boolean;
  } | null>(null);

  // Commit state
  const [committing, setCommitting] = useState(false);

  // Resolve effective group ID
  const effectiveGroupId = showCustomGroup
    ? customGroup.trim() || 'default'
    : groupId || 'default';

  // Fetch groups on mount — prefer stored group, fall back to first available
  useEffect(() => {
    fetch('/api/graph/groups', { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: GroupOption[]) => {
        setGroups(data);
        if (
          storedGroupId &&
          storedGroupId !== 'all' &&
          data.some((g) => (g.id || g.name) === storedGroupId)
        ) {
          setGroupId(storedGroupId);
        } else if (data.length > 0) {
          setGroupId(data[0].id || data[0].name);
        }
      })
      .catch(() => {});

    // Fetch available schemas
    fetch('/api/schemas', { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: SchemaOption[]) => setSchemas(data))
      .catch(() => {});
  }, []);

  // Fetch schema detail when selection changes
  useEffect(() => {
    if (schemaId === null) {
      return;
    }
    let cancelled = false;
    // Reset detail synchronously via fetch of new data
    fetch(`/api/schemas/${schemaId}`, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: SchemaDetail | null) => {
        if (!cancelled) setSchemaDetail(data);
      })
      .catch(() => {
        if (!cancelled) setSchemaDetail(null);
      });
    return () => {
      cancelled = true;
      setSchemaDetail(null);
    };
  }, [schemaId]);

  // -----------------------------------------------------------------------
  // Stage progress helper
  // -----------------------------------------------------------------------

  const getStageStatus = (stageKey: string): 'done' | 'active' | 'pending' => {
    const currentIdx = STAGES.findIndex((s) => s.key === stage);
    const stageIdx = STAGES.findIndex((s) => s.key === stageKey);
    if (stageIdx < 0 || currentIdx < 0) return 'pending';
    if (stageIdx < currentIdx) return 'done';
    if (stageIdx === currentIdx) return 'active';
    return 'pending';
  };

  const progressPercent =
    step === 'processing'
      ? Math.round(
          ((STAGES.findIndex((s) => s.key === stage) + 1) / STAGES.length) * 100,
        )
      : 0;

  // -----------------------------------------------------------------------
  // File upload handler
  // -----------------------------------------------------------------------

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    try {
      const text = await file.text();
      setContent(text);
      if (!name) setName(file.name.replace(/\.[^.]+$/, ''));
    } catch {
      setPollError('文件读取失败');
    }
  };

  // -----------------------------------------------------------------------
  // Preview handler
  // -----------------------------------------------------------------------

  const handlePreview = useCallback(async () => {
    if (!content.trim() || submittingRef.current) return;
    submittingRef.current = true;
    setStep('processing');
    setPollError(null);
    cancelRef.current = false;
    setStage('');
    taskIdRef.current = null;
    setTaskId(null); // clear stale taskId from previous attempt

    try {
      const res = await fetch('/api/knowledge/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name || fileName || `Preview: ${content.slice(0, 50)}`,
          content,
          group_id: effectiveGroupId,
          source,
          source_description: 'Knowledge page ingest',
          schema_id: schemaId,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Preview submit failed' }));
        throw new Error(err.error);
      }
      const { task_id } = await res.json();
      taskIdRef.current = task_id;
      setTaskId(task_id); // triggers polling useEffect
    } catch (err) {
      setPollError(err instanceof Error ? err.message : 'Unknown error');
      setTaskId(null);
      setStep('input');
    } finally {
      submittingRef.current = false;
    }
  }, [content, name, effectiveGroupId, source, fileName, schemaId]);

  // -----------------------------------------------------------------------
  // Polling loop — tied to component lifecycle via useEffect
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!taskId) return;
    if (step !== 'processing') return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let consecutiveErrors = 0;

    const poll = async () => {
      if (cancelled || cancelRef.current) {
        if (cancelRef.current) setStep('input');
        return;
      }

      try {
        const res = await fetch(
          `/api/knowledge/preview/${encodeURIComponent(taskId)}`,
        );

        // Check cancelled again after async fetch resolves
        if (cancelled || cancelRef.current) return;

        if (!res.ok) {
          // Non-OK response (502, 504, etc.) — skip and retry
          consecutiveErrors++;
          if (consecutiveErrors >= POLL_MAX_CONSECUTIVE_ERRORS) {
            setPollError('服务器连接异常，请稍后重试');
            setTaskId(null);
            setStep('input');
            return;
          }
          timer = setTimeout(poll, 2000);
          return;
        }

        // Guard: poll.json() may throw on non-JSON responses (e.g. proxy HTML error pages)
        let data: { stage?: string; status?: string; result?: unknown; error?: string };
        try {
          data = await res.json();
        } catch {
          consecutiveErrors++;
          if (consecutiveErrors >= POLL_MAX_CONSECUTIVE_ERRORS) {
            setPollError('服务器响应格式异常，请稍后重试');
            setTaskId(null);
            setStep('input');
            return;
          }
          timer = setTimeout(poll, 2000);
          return;
        }

        // Check cancelled again after JSON parsing
        if (cancelled || cancelRef.current) return;

        // Successful parse — reset consecutive error counter
        consecutiveErrors = 0;
        setStage(data.stage || '');

        if (data.status === 'completed' && data.result) {
          setPreview(data.result as PreviewMemoryResponse);
          setStep('review');
          return;
        }
        if (data.status === 'failed') {
          setPollError(data.error || '提取失败');
          setTaskId(null);
          setStep('input');
          return;
        }

        // Still processing — schedule next poll
        timer = setTimeout(poll, 2000);
      } catch {
        // Network error (fetch itself failed)
        if (cancelled || cancelRef.current) return;
        consecutiveErrors++;
        if (consecutiveErrors >= POLL_MAX_CONSECUTIVE_ERRORS) {
          setPollError('网络连接异常，请稍后重试');
          setTaskId(null);
          setStep('input');
          return;
        }
        timer = setTimeout(poll, 2000);
      }
    };

    // Kick off polling
    poll();

    return () => {
      cancelled = true;
      cancelRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [taskId, step]);

  // -----------------------------------------------------------------------
  // Direct generate handler
  // -----------------------------------------------------------------------

  const handleDirectGenerate = useCallback(async () => {
    if (!content.trim()) return;
    setStep('processing');
    setPollError(null);

    try {
      const res = await fetch('/api/knowledge/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name || fileName || content.slice(0, 50),
          content,
          group_id: effectiveGroupId,
          source,
          schema_id: schemaId,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Submit failed' }));
        throw new Error(err.error);
      }
      router.push('/knowledge');
    } catch (err) {
      setPollError(err instanceof Error ? err.message : 'Submit failed');
      setStep('input');
    }
  }, [content, name, effectiveGroupId, source, fileName, schemaId, router]);

  // -----------------------------------------------------------------------
  // Commit handler
  // -----------------------------------------------------------------------

  const handleCommit = useCallback(async () => {
    if (!preview) return;
    setCommitting(true);

    try {
      const confirmedNodes = preview.nodes.filter((n) => !excludedNodeIds.has(n.uuid));
      const confirmedEdges = preview.edges.filter((e) => !excludedEdgeIds.has(e.uuid));

      const res = await fetch('/api/knowledge/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          episode: preview.episode,
          nodes: confirmedNodes,
          edges: confirmedEdges,
          group_id: effectiveGroupId,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Commit failed' }));
        throw new Error(err.error);
      }

      router.push('/knowledge');
    } catch (err) {
      window.alert(`提交失败: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setCommitting(false);
    }
  }, [preview, excludedNodeIds, excludedEdgeIds, effectiveGroupId, router]);

  // -----------------------------------------------------------------------
  // CRUD handlers for nodes and edges
  // -----------------------------------------------------------------------

  const handleSaveNode = useCallback(
    (uuid: string, data: { name: string; labels: string[]; summary: string }) => {
      setPreview((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((n) =>
            n.uuid === uuid ? { ...n, ...data } : n,
          ),
          edges: prev.edges.map((e) => ({
            ...e,
            source_node_name:
              e.source_node_uuid === uuid ? data.name : e.source_node_name,
            target_node_name:
              e.target_node_uuid === uuid ? data.name : e.target_node_name,
          })),
        };
      });
    },
    [],
  );

  const handleDeleteNode = useCallback(
    (uuid: string) => {
      setPreview((prev) => {
        if (!prev) return prev;
        const affectedEdges = prev.edges.filter(
          (e) => e.source_node_uuid === uuid || e.target_node_uuid === uuid,
        );
        if (affectedEdges.length > 0) {
          const confirmed = window.confirm(
            `删除该节点将同时删除 ${affectedEdges.length} 条关联关系，是否继续？`,
          );
          if (!confirmed) return prev;
        }
        return {
          ...prev,
          nodes: prev.nodes.filter((n) => n.uuid !== uuid),
          edges: prev.edges.filter(
            (e) => e.source_node_uuid !== uuid && e.target_node_uuid !== uuid,
          ),
        };
      });
      // Also clean up excluded sets
      setExcludedNodeIds((prev) => {
        const next = new Set(prev);
        next.delete(uuid);
        return next;
      });
    },
    [],
  );

  const handleAddNode = useCallback(() => {
    const newNode: NodePreview = {
      uuid: generateUUID(),
      name: '',
      labels: ['Entity'],
      summary: '',
      group_id: effectiveGroupId,
      is_new: true,
    };
    setEditingNode({ node: newNode, isNew: true });
  }, [effectiveGroupId]);

  const handleNodeDialogSave = useCallback(
    (uuid: string, data: { name: string; labels: string[]; summary: string }) => {
      if (editingNode?.isNew) {
        // Adding a new node
        const newNode: NodePreview = {
          uuid,
          ...data,
          group_id: effectiveGroupId,
          is_new: true,
        };
        setPreview((prev) =>
          prev ? { ...prev, nodes: [...prev.nodes, newNode] } : prev,
        );
      } else {
        handleSaveNode(uuid, data);
      }
    },
    [editingNode, effectiveGroupId, handleSaveNode],
  );

  const handleSaveEdge = useCallback(
    (
      uuid: string,
      data: {
        name: string;
        fact: string;
        source_node_uuid: string;
        target_node_uuid: string;
      },
    ) => {
      setPreview((prev) => {
        if (!prev) return prev;
        const sourceNode = prev.nodes.find((n) => n.uuid === data.source_node_uuid);
        const targetNode = prev.nodes.find((n) => n.uuid === data.target_node_uuid);
        return {
          ...prev,
          edges: prev.edges.map((e) =>
            e.uuid === uuid
              ? {
                  ...e,
                  ...data,
                  source_node_name: sourceNode?.name || '',
                  target_node_name: targetNode?.name || '',
                }
              : e,
          ),
        };
      });
    },
    [],
  );

  const handleDeleteEdge = useCallback((uuid: string) => {
    setPreview((prev) =>
      prev ? { ...prev, edges: prev.edges.filter((e) => e.uuid !== uuid) } : prev,
    );
    setExcludedEdgeIds((prev) => {
      const next = new Set(prev);
      next.delete(uuid);
      return next;
    });
  }, []);

  const handleAddEdge = useCallback(() => {
    const newEdge: EdgePreview = {
      uuid: generateUUID(),
      name: '',
      fact: '',
      source_node_uuid: '',
      source_node_name: '',
      target_node_uuid: '',
      target_node_name: '',
      valid_at: null,
      invalid_at: null,
      expired_at: null,
    };
    setEditingEdge({ edge: newEdge, isNew: true });
  }, []);

  const handleEdgeDialogSave = useCallback(
    (
      uuid: string,
      data: {
        name: string;
        fact: string;
        source_node_uuid: string;
        target_node_uuid: string;
      },
    ) => {
      if (editingEdge?.isNew) {
        // Adding a new edge
        const sourceNode = preview?.nodes.find((n) => n.uuid === data.source_node_uuid);
        const targetNode = preview?.nodes.find((n) => n.uuid === data.target_node_uuid);
        const newEdge: EdgePreview = {
          uuid,
          ...data,
          source_node_name: sourceNode?.name || '',
          target_node_name: targetNode?.name || '',
          valid_at: null,
          invalid_at: null,
          expired_at: null,
        };
        setPreview((prev) =>
          prev ? { ...prev, edges: [...prev.edges, newEdge] } : prev,
        );
      } else {
        handleSaveEdge(uuid, data);
      }
    },
    [editingEdge, preview, handleSaveEdge],
  );

  // Available nodes for edge editing (not excluded)
  const availableNodesForEdges = preview
    ? preview.nodes.filter((n) => !excludedNodeIds.has(n.uuid))
    : [];

  // -----------------------------------------------------------------------
  // Toggle helpers
  // -----------------------------------------------------------------------

  const toggleNode = (uuid: string) =>
    setExcludedNodeIds((prev) => {
      const next = new Set(prev);
      next.has(uuid) ? next.delete(uuid) : next.add(uuid);
      return next;
    });

  const toggleEdge = (uuid: string) =>
    setExcludedEdgeIds((prev) => {
      const next = new Set(prev);
      next.has(uuid) ? next.delete(uuid) : next.add(uuid);
      return next;
    });

  // -----------------------------------------------------------------------
  // LEFT PANEL — Input
  // -----------------------------------------------------------------------

  const renderLeftPanel = () => (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <Button variant="ghost" size="icon" onClick={() => router.push('/knowledge')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">新建知识</h1>
          <p className="text-xs text-muted-foreground">输入内容并提取实体与关系</p>
        </div>
      </div>

      {/* Scrollable form */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
        {pollError && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3">
            <p className="text-sm text-destructive">{pollError}</p>
          </div>
        )}

        {/* Group */}
        <div className="space-y-2">
          <Label>分组</Label>
          {showCustomGroup ? (
            <div className="flex gap-2">
              <Input
                placeholder="输入新分组名称"
                value={customGroup}
                onChange={(e) => setCustomGroup(e.target.value)}
                className="flex-1"
                autoFocus
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowCustomGroup(false);
                  setCustomGroup('');
                }}
              >
                取消
              </Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <select
                value={groupId}
                onChange={(e) => {
                  setGroupId(e.target.value);
                  setStoredGroup(e.target.value); // sync to shared store
                }}
                className="h-9 flex-1 rounded-md border bg-background px-3 text-sm"
              >
                {groups.length === 0 && <option value="default">default</option>}
                {groups.map((g) => (
                  <option key={g.id || g.name} value={g.id || g.name}>
                    {g.id || g.name}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCustomGroup(true)}
                title="创建新分组"
              >
                + 新建
              </Button>
            </div>
          )}
        </div>

        {/* Advanced options (collapsed) */}
        <button
          type="button"
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          <Settings2 className="h-3.5 w-3.5" />
          高级选项
          <ChevronRight
            className={cn('h-3 w-3 transition-transform', showAdvanced && 'rotate-90')}
          />
        </button>
        {showAdvanced && (
          <div className="grid grid-cols-2 gap-4 rounded-lg border bg-muted/30 p-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Source Type</Label>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="h-8 w-full rounded-md border bg-background px-2 text-xs"
              >
                <option value="text">Text</option>
                <option value="message">Message</option>
                <option value="json">JSON</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Name (optional)</Label>
              <Input
                placeholder="自动生成"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-8 text-xs"
              />
            </div>
          </div>
        )}

        {/* Generation mode */}
        <div className="space-y-1.5">
          <Label className="text-xs">生成模式</Label>
          <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
            <button
              type="button"
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                mode === 'preview'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              onClick={() => setMode('preview')}
            >
              <Check className="h-3.5 w-3.5" />
              审查模式
            </button>
            <button
              type="button"
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                mode === 'direct'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              onClick={() => setMode('direct')}
            >
              <Send className="h-3.5 w-3.5" />
              直接生成
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {mode === 'preview'
              ? '预览提取结果，手动确认后写入图谱'
              : '自动提取并写入，无需审查'}
          </p>
        </div>

        {/* Schema selector */}
        <div className="space-y-1.5">
          <Label className="text-xs">Extraction Schema</Label>
          <select
            value={schemaId ?? ''}
            onChange={(e) => setSchemaId(e.target.value ? Number(e.target.value) : null)}
            className="h-8 w-full rounded-md border bg-background px-2 text-xs"
          >
            <option value="">不使用 Schema（默认）</option>
            {schemas.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} — {s.entity_type_count} 实体 / {s.edge_type_count} 关系
              </option>
            ))}
          </select>
          {schemaId !== null && schemaDetail && (
            <div className="flex flex-wrap gap-1 pt-1">
              {schemaDetail.entity_types.map((et) => (
                <Badge key={`e-${et.name}`} variant="secondary" className="text-[10px]">
                  {et.name}
                </Badge>
              ))}
              {schemaDetail.edge_types.map((et) => (
                <Badge key={`r-${et.name}`} variant="outline" className="text-[10px]">
                  {et.name}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Input mode toggle */}
        <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            className={cn(
              'flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              inputMode === 'text'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setInputMode('text')}
          >
            <Type className="h-4 w-4" />
            粘贴文本
          </button>
          <button
            type="button"
            className={cn(
              'flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              inputMode === 'file'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setInputMode('file')}
          >
            <Upload className="h-4 w-4" />
            上传文件
          </button>
        </div>

        {/* Content area */}
        {inputMode === 'text' ? (
          <div className="flex flex-1 flex-col space-y-1.5">
            <Label>内容</Label>
            <textarea
              className="flex-1 min-h-[200px] w-full resize-y rounded-md border bg-background p-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="粘贴或输入文本内容..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{content.length} 字符</p>
          </div>
        ) : (
          <div className="space-y-3">
            <Label>文件</Label>
            <div
              className={cn(
                'flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer',
                fileName
                  ? 'border-primary/30 bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-primary/40 hover:bg-muted/30',
              )}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.json,.csv,.html,.xml,.yaml,.yml,.log,.py,.js,.ts,.tsx,.jsx"
                className="hidden"
                onChange={handleFileUpload}
              />
              {fileName ? (
                <>
                  <FileText className="mb-2 h-10 w-10 text-primary" />
                  <p className="text-sm font-medium">{fileName}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {content.length} 字符已加载 — 点击重新选择
                  </p>
                </>
              ) : (
                <>
                  <Upload className="mb-2 h-10 w-10 text-muted-foreground" />
                  <p className="text-sm font-medium">点击选择文件</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    支持 .txt, .md, .json, .csv, .html, .xml 等文本文件
                  </p>
                </>
              )}
            </div>
            {content && (
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">内容预览</Label>
                <pre className="max-h-[160px] overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
                  {content.slice(0, 1000)}
                  {content.length > 1000 && '\n...'}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom action */}
      <div className="border-t px-6 py-3">
        {mode === 'preview' ? (
          <>
            <Button className="w-full" onClick={handlePreview} disabled={!content.trim()}>
              预览提取
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
            <p className="mt-1.5 text-center text-xs text-muted-foreground">
              提取将分析内容中的实体和关系
            </p>
          </>
        ) : (
          <>
            <Button className="w-full" onClick={handleDirectGenerate} disabled={!content.trim()}>
              <Send className="mr-1 h-4 w-4" />
              直接生成
            </Button>
            <p className="mt-1.5 text-center text-xs text-muted-foreground">
              提交到处理队列，自动提取并写入图谱
            </p>
          </>
        )}
      </div>
    </div>
  );

  // -----------------------------------------------------------------------
  // RIGHT PANEL — Processing / Review
  // -----------------------------------------------------------------------

  const renderRightPanel = () => {
    if (step === 'input') {
      return (
        <div className="flex h-full flex-col items-center justify-center text-muted-foreground">
          <div className="rounded-2xl border-2 border-dashed p-12 text-center">
            <ChevronRight className="mx-auto mb-3 h-8 w-8 opacity-40" />
            <p className="text-sm font-medium">在左侧输入内容</p>
            <p className="mt-1 text-xs">
              {mode === 'preview'
                ? '点击"预览提取"后，提取结果将在此展示'
                : '切换为审查模式可在此预览提取结果'}
            </p>
          </div>
        </div>
      );
    }

    if (step === 'processing') {
      return (
        <div className="flex h-full flex-col items-center justify-center px-8">
          <div className="w-full max-w-md space-y-6">
            {/* Progress bar */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">处理中...</span>
                <span className="text-muted-foreground">{progressPercent}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Stage list */}
            <div className="space-y-1">
              {STAGES.map((s) => {
                const st = getStageStatus(s.key);
                return (
                  <div
                    key={s.key}
                    className={cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                      st === 'active' && 'bg-primary/5',
                    )}
                  >
                    {st === 'done' && (
                      <Check className="h-4 w-4 shrink-0 text-green-600" />
                    )}
                    {st === 'active' && (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                    )}
                    {st === 'pending' && (
                      <div className="h-4 w-4 shrink-0 rounded-full border-2 border-muted" />
                    )}
                    <span
                      className={cn(
                        st === 'done' && 'text-muted-foreground line-through',
                        st === 'active' && 'font-medium text-foreground',
                        st === 'pending' && 'text-muted-foreground',
                      )}
                    >
                      {s.label}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="flex justify-center">
              <Button
                variant="outline"
                onClick={() => {
                  cancelRef.current = true;
                }}
              >
                取消
              </Button>
            </div>
          </div>
        </div>
      );
    }

    // step === 'review'
    if (!preview) return null;

    const activeNodes = preview.nodes.filter((n) => !excludedNodeIds.has(n.uuid));
    const activeEdges = preview.edges.filter((e) => !excludedEdgeIds.has(e.uuid));

    return (
      <div className="flex h-full flex-col">
        {/* Review header */}
        <div className="flex items-center justify-between border-b px-6 py-3">
          <div>
            <h2 className="text-sm font-semibold">审查提取结果</h2>
            <p className="text-xs text-muted-foreground">
              {activeNodes.length} 个实体，{activeEdges.length} 条关系待写入
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setStep('input')}>
            <ArrowLeft className="mr-1 h-3.5 w-3.5" />
            返回编辑
          </Button>
        </div>

        {/* Scrollable review content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* Original content (collapsible) */}
          <details className="group rounded-lg border">
            <summary className="flex cursor-pointer items-center justify-between px-4 py-2.5 text-sm font-medium">
              原始内容
              <span className="text-xs text-muted-foreground">
                {preview.episode.content.length} 字符
              </span>
            </summary>
            <div className="border-t px-4 py-3">
              <pre className="max-h-[120px] overflow-y-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                {preview.episode.content}
              </pre>
            </div>
          </details>

          {/* Entities */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">
                实体 ({preview.nodes.length})
                {excludedNodeIds.size > 0 && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    已排除 {excludedNodeIds.size}
                  </span>
                )}
              </h3>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={handleAddNode}
              >
                <Plus className="mr-0.5 h-3 w-3" />
                新建
              </Button>
            </div>
            {preview.nodes.length === 0 ? (
              <p className="rounded-lg border bg-muted/30 py-6 text-center text-sm text-muted-foreground">
                未提取到实体
              </p>
            ) : (
              <div className="space-y-1.5">
                {preview.nodes.map((node) => {
                  const excluded = excludedNodeIds.has(node.uuid);
                  return (
                    <div
                      key={node.uuid}
                      className={cn(
                        'flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
                        excluded ? 'opacity-40' : 'hover:bg-muted/30',
                      )}
                    >
                      <button
                        onClick={() => toggleNode(node.uuid)}
                        className={cn(
                          'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors',
                          excluded
                            ? 'border-destructive/50 text-destructive'
                            : 'border-green-500/50 text-green-600',
                        )}
                      >
                        {excluded ? (
                          <X className="h-3 w-3" />
                        ) : (
                          <Check className="h-3 w-3" />
                        )}
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{node.name}</span>
                          {node.is_new && (
                            <Badge variant="secondary" className="text-[10px]">
                              NEW
                            </Badge>
                          )}
                          {node.labels.map((l) => (
                            <Badge key={l} variant="outline" className="text-[10px]">
                              {l}
                            </Badge>
                          ))}
                        </div>
                        {node.summary && (
                          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                            {node.summary}
                          </p>
                        )}
                      </div>
                      {!excluded && (
                        <div className="flex shrink-0 items-center gap-0.5">
                          <button
                            onClick={() => setEditingNode({ node, isNew: false })}
                            className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
                            title="编辑"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteNode(node.uuid)}
                            className="rounded p-1 text-muted-foreground hover:text-destructive transition-colors"
                            title="删除"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Relationships */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">
                关系 ({preview.edges.length})
                {excludedEdgeIds.size > 0 && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    已排除 {excludedEdgeIds.size}
                  </span>
                )}
              </h3>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={handleAddEdge}
                disabled={availableNodesForEdges.length < 1}
                title={availableNodesForEdges.length < 1 ? '请先添加节点' : '新建关系'}
              >
                <Plus className="mr-0.5 h-3 w-3" />
                新建
              </Button>
            </div>
            {preview.edges.length === 0 ? (
              <p className="rounded-lg border bg-muted/30 py-6 text-center text-sm text-muted-foreground">
                未提取到关系
              </p>
            ) : (
              <div className="space-y-1.5">
                {preview.edges.map((edge) => {
                  const excluded = excludedEdgeIds.has(edge.uuid);
                  return (
                    <div
                      key={edge.uuid}
                      className={cn(
                        'flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
                        excluded ? 'opacity-40' : 'hover:bg-muted/30',
                      )}
                    >
                      <button
                        onClick={() => toggleEdge(edge.uuid)}
                        className={cn(
                          'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors',
                          excluded
                            ? 'border-destructive/50 text-destructive'
                            : 'border-green-500/50 text-green-600',
                        )}
                      >
                        {excluded ? (
                          <X className="h-3 w-3" />
                        ) : (
                          <Check className="h-3 w-3" />
                        )}
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 text-sm">
                          <span className="font-medium">
                            {edge.source_node_name || edge.source_node_uuid.slice(0, 8)}
                          </span>
                          <span className="text-muted-foreground">→</span>
                          <span className="font-medium">
                            {edge.target_node_name || edge.target_node_uuid.slice(0, 8)}
                          </span>
                        </div>
                        {edge.name && (
                          <Badge variant="outline" className="mt-0.5 text-[10px]">
                            {edge.name}
                          </Badge>
                        )}
                        {edge.fact && (
                          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                            {edge.fact}
                          </p>
                        )}
                      </div>
                      {!excluded && (
                        <div className="flex shrink-0 items-center gap-0.5">
                          <button
                            onClick={() => setEditingEdge({ edge, isNew: false })}
                            className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
                            title="编辑"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteEdge(edge.uuid)}
                            className="rounded p-1 text-muted-foreground hover:text-destructive transition-colors"
                            title="删除"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Invalidated edges */}
          {preview.invalidated_edges.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-muted-foreground">
                失效关系 ({preview.invalidated_edges.length})
              </h3>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {preview.invalidated_edges.map((e) => (
                  <li key={e.uuid} className="line-through">
                    {e.source_node_name} — {e.fact} — {e.target_node_name}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Sticky commit bar */}
        <div className="flex items-center justify-between border-t bg-background px-6 py-3">
          <Button variant="outline" onClick={() => setStep('input')}>
            <ArrowLeft className="mr-1 h-3.5 w-3.5" />
            返回
          </Button>
          <Button onClick={handleCommit} disabled={committing}>
            {committing ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                写入中...
              </>
            ) : (
              <>
                <Check className="mr-1 h-4 w-4" />
                写入图谱 ({activeNodes.length} 实体, {activeEdges.length} 关系)
              </>
            )}
          </Button>
        </div>

        {/* Edit dialogs */}
        <NodeEditDialog
          open={!!editingNode}
          onOpenChange={(open) => { if (!open) setEditingNode(null); }}
          node={editingNode?.node ?? null}
          isNew={editingNode?.isNew ?? false}
          onSave={handleNodeDialogSave}
        />
        <EdgeEditDialog
          open={!!editingEdge}
          onOpenChange={(open) => { if (!open) setEditingEdge(null); }}
          edge={editingEdge?.edge ?? null}
          isNew={editingEdge?.isNew ?? false}
          nodes={availableNodesForEdges}
          onSave={handleEdgeDialogSave}
        />
      </div>
    );
  };

  // -----------------------------------------------------------------------
  // Main layout
  // -----------------------------------------------------------------------

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Left panel — Input */}
      <div className="w-[40%] min-w-[360px] border-r bg-card">
        {renderLeftPanel()}
      </div>

      {/* Right panel — Processing / Review */}
      <div className="flex-1 bg-background">{renderRightPanel()}</div>
    </div>
  );
}
