'use client';

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

// Built-in entity type candidates (mirrors server DEFAULT_ENTITY_TYPES)
const ENTITY_TYPE_CANDIDATES = [
  'Person',
  'Organization',
  'Location',
  'Object',
  'Document',
  'Event',
  'Topic',
];

interface NodeData {
  uuid: string;
  name: string;
  labels: string[];
  summary: string;
}

interface NodeEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  node: NodeData | null;
  isNew: boolean;
  onSave: (uuid: string, data: { name: string; labels: string[]; summary: string }) => void;
}

export function NodeEditDialog({
  open,
  onOpenChange,
  node,
  isNew,
  onSave,
}: NodeEditDialogProps) {
  const [name, setName] = useState('');
  const [labels, setLabels] = useState('');
  const [summary, setSummary] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (node) {
      setName(node.name);
      setLabels(node.labels.join(', '));
      setSummary(node.summary);
      setError(null);
    }
  }, [node]);

  const handleSave = () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('名称不能为空');
      return;
    }
    const parsedLabels = labels
      .split(',')
      .map((l) => l.trim())
      .filter(Boolean);
    if (!node) return;
    onSave(node.uuid, { name: trimmedName, labels: parsedLabels, summary: summary.trim() });
    onOpenChange(false);
  };

  const toggleCandidate = (candidate: string) => {
    const current = labels.split(',').map((l) => l.trim()).filter(Boolean);
    const idx = current.indexOf(candidate);
    if (idx >= 0) {
      current.splice(idx, 1);
    } else {
      current.push(candidate);
    }
    setLabels(current.join(', '));
  };

  const isCandidateActive = (candidate: string) => {
    const current = labels.split(',').map((l) => l.trim()).filter(Boolean);
    return current.includes(candidate);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isNew ? '新建实体' : '编辑实体'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="space-y-1.5">
            <Label className="text-xs">名称 *</Label>
            <Input
              value={name}
              onChange={(e) => { setName(e.target.value); setError(null); }}
              placeholder="实体名称"
              className="h-8 text-sm"
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
            />
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">标签（逗号分隔）</Label>
            <Input
              value={labels}
              onChange={(e) => setLabels(e.target.value)}
              placeholder="Person, CEO"
              className="h-8 text-sm"
            />
            {/* Type candidates */}
            <div className="flex flex-wrap gap-1 pt-1">
              {ENTITY_TYPE_CANDIDATES.map((candidate) => (
                <button
                  key={candidate}
                  type="button"
                  onClick={() => toggleCandidate(candidate)}
                  className={
                    'rounded-full border px-2 py-0.5 text-xs transition-colors ' +
                    (isCandidateActive(candidate)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-muted-foreground/30 text-muted-foreground hover:border-primary/50')
                  }
                >
                  {candidate}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">摘要</Label>
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="实体描述..."
              rows={3}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={!name.trim()}>
            {isNew ? '添加' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
