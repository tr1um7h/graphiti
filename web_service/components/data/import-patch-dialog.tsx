'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Upload } from 'lucide-react';
import type { GroupStats, PatchPreview, ConflictStrategy } from '@/lib/types';
import { DryRunDialog } from './dry-run-dialog';

interface ImportPatchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  targetGroupId: string;
  groups: GroupStats[];
  onApplied: () => void;
}

export function ImportPatchDialog({
  open,
  onOpenChange,
  targetGroupId,
  groups,
  onApplied,
}: ImportPatchDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PatchPreview | null>(null);
  const [patchContent, setPatchContent] = useState<unknown>(null);
  const [fromGroupId, setFromGroupId] = useState('');
  const [toGroupId, setToGroupId] = useState('');
  const [strategy, setStrategy] = useState<ConflictStrategy>('ours');
  const [dryRun, setDryRun] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dryRunResult, setDryRunResult] = useState<unknown>(null);
  const [showDryRunDialog, setShowDryRunDialog] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setError(null);
    setPreview(null);
    setPatchContent(null);

    try {
      // Read file for preview
      const formData = new FormData();
      formData.append('file', selectedFile);

      const res = await fetch('/api/data/patch/preview', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Preview failed' }));
        throw new Error(err.error || err.detail || 'Preview failed');
      }

      const data = await res.json();
      setPreview(data);
      setFromGroupId(data.metadata?.from_group_id || '');
      setToGroupId(targetGroupId);

      // Also read the full patch content for applying
      const text = await selectedFile.text();
      setPatchContent(JSON.parse(text));
    } catch (err) {
      console.error('Preview failed:', err);
      setError(err instanceof Error ? err.message : 'Preview failed');
    }
  };

  const handleApply = async () => {
    if (!patchContent || !toGroupId) {
      setError('Please select a file and target group');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/data/patch/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patch: patchContent,
          from_group_id: fromGroupId || undefined,
          to_group_id: toGroupId,
          strategy,
          dry_run: dryRun,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Apply failed' }));
        throw new Error(err.error || err.detail || 'Apply failed');
      }

      const result = await res.json();

      if (dryRun) {
        setDryRunResult(result);
        setShowDryRunDialog(true);
      } else {
        console.log('Patch applied:', result);
        onApplied();
        resetDialog();
      }
    } catch (err) {
      console.error('Apply failed:', err);
      setError(err instanceof Error ? err.message : 'Apply failed');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmExecute = async () => {
    setShowDryRunDialog(false);
    setDryRun(false);
    await handleApply();
  };

  const resetDialog = () => {
    setFile(null);
    setPreview(null);
    setPatchContent(null);
    setFromGroupId('');
    setToGroupId(targetGroupId);
    setStrategy('ours');
    setDryRun(false);
    setError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.name.endsWith('.json')) {
      const input = document.getElementById('patch-file-input') as HTMLInputElement;
      if (input) {
        const dt = new DataTransfer();
        dt.items.add(droppedFile);
        input.files = dt.files;
        handleFileChange({ target: input } as React.ChangeEvent<HTMLInputElement>);
      }
    } else {
      setError('Please drop a JSON file');
    }
  };

  const totalChanges = preview
    ? Object.values(preview.summary).reduce(
        (acc, s) => ({
          added: acc.added + s.added,
          removed: acc.removed + s.removed,
          modified: acc.modified + s.modified,
          conflicts: acc.conflicts + s.conflicts,
        }),
        { added: 0, removed: 0, modified: 0, conflicts: 0 }
      )
    : null;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import Patch</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {/* File upload */}
            <div>
              <Label>Upload Patch File</Label>
              <div
                className="mt-2 border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => document.getElementById('patch-file-input')?.click()}
              >
                <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                {file ? (
                  <p className="text-sm">{file.name}</p>
                ) : (
                  <>
                    <p className="text-sm font-medium">Click to select or drop file here</p>
                    <p className="text-xs text-muted-foreground mt-1">JSON file required</p>
                  </>
                )}
                <input
                  id="patch-file-input"
                  type="file"
                  accept=".json"
                  onChange={handleFileChange}
                  className="hidden"
                />
              </div>
            </div>

            {/* Preview */}
            {preview && (
              <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
                <div>
                  <Label className="text-sm font-semibold">Patch Preview</Label>
                  <div className="mt-2 text-sm space-y-1">
                    <p>
                      <span className="text-muted-foreground">From:</span>{' '}
                      <span className="font-medium">{preview.metadata?.from_group_id || 'N/A'}</span>
                    </p>
                    <p>
                      <span className="text-muted-foreground">To:</span>{' '}
                      <span className="font-medium">{preview.metadata?.to_group_id || 'N/A'}</span>
                    </p>
                  </div>
                </div>

                <div>
                  <Label className="text-sm font-semibold">Changes</Label>
                  <div className="mt-2 space-y-2">
                    {Object.entries(preview.summary).map(([table, counts]) => (
                      <div key={table} className="text-sm flex items-center gap-4">
                        <span className="font-medium w-40">{table}</span>
                        <span className="text-green-600">+{counts.added}</span>
                        <span className="text-red-600">-{counts.removed}</span>
                        <span className="text-blue-600">~{counts.modified}</span>
                        {counts.conflicts > 0 && (
                          <span className="text-orange-600">!{counts.conflicts}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {totalChanges && (
                  <div className="border-t pt-2 text-sm font-semibold flex items-center gap-4">
                    <span className="w-40">Total</span>
                    <span className="text-green-600">+{totalChanges.added}</span>
                    <span className="text-red-600">-{totalChanges.removed}</span>
                    <span className="text-blue-600">~{totalChanges.modified}</span>
                    {totalChanges.conflicts > 0 && (
                      <span className="text-orange-600">!{totalChanges.conflicts}</span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* From Group ID */}
            <div>
              <Label htmlFor="from-group">Source Group ID (from)</Label>
              <input
                id="from-group"
                value={fromGroupId}
                onChange={(e) => setFromGroupId(e.target.value)}
                placeholder="Default from patch metadata"
                className="mt-2 w-full h-9 rounded-md border bg-background px-3 text-sm"
              />
            </div>

            {/* To Group ID */}
            <div>
              <Label htmlFor="to-group">Apply to Group (to)</Label>
              <select
                id="to-group"
                value={toGroupId}
                onChange={(e) => setToGroupId(e.target.value)}
                className="mt-2 w-full h-9 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">Select target group...</option>
                {groups.map((g) => (
                  <option key={g.group_id} value={g.group_id}>
                    {g.group_id}
                  </option>
                ))}
              </select>
            </div>

            {/* Strategy */}
            <div>
              <Label>Conflict Strategy</Label>
              <div className="mt-2 space-y-2">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="strategy"
                    value="ours"
                    checked={strategy === 'ours'}
                    onChange={(e) => setStrategy(e.target.value as ConflictStrategy)}
                  />
                  <span className="text-sm">
                    <span className="font-medium">Ours</span> — Keep target data, skip conflicts
                  </span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="strategy"
                    value="theirs"
                    checked={strategy === 'theirs'}
                    onChange={(e) => setStrategy(e.target.value as ConflictStrategy)}
                  />
                  <span className="text-sm">
                    <span className="font-medium">Theirs</span> — Use patch data, overwrite conflicts
                  </span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="strategy"
                    value="skip-conflicts"
                    checked={strategy === 'skip-conflicts'}
                    onChange={(e) => setStrategy(e.target.value as ConflictStrategy)}
                  />
                  <span className="text-sm">
                    <span className="font-medium">Skip</span> — Skip entire tables with conflicts
                  </span>
                </label>
              </div>
            </div>

            {/* Dry Run checkbox */}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="dry-run"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="rounded border-gray-300"
              />
              <Label htmlFor="dry-run" className="text-sm font-normal">
                Dry Run (preview only, no changes)
              </Label>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleApply}
                disabled={loading || !file || !toGroupId}
                className={dryRun ? 'bg-blue-600 hover:bg-blue-700' : ''}
              >
                {loading ? 'Processing...' : dryRun ? 'Run Dry Run' : 'Apply Patch'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <DryRunDialog
        open={showDryRunDialog}
        onOpenChange={setShowDryRunDialog}
        result={dryRunResult as import('@/lib/types').PatchApplyResult | null}
        onConfirmExecute={handleConfirmExecute}
        onCancel={() => {
          setShowDryRunDialog(false);
          resetDialog();
        }}
      />
    </>
  );
}
