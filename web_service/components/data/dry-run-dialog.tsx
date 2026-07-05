'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

interface DryRunResult {
  success: boolean;
  dry_run: boolean;
  added: number;
  removed: number;
  modified: number;
  conflicts: number;
}

interface DryRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  result: DryRunResult | null;
  onConfirmExecute: () => void;
  onCancel: () => void;
}

export function DryRunDialog({
  open,
  onOpenChange,
  result,
  onConfirmExecute,
  onCancel,
}: DryRunDialogProps) {
  if (!result) return null;

  const hasConflicts = result.conflicts > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            Dry Run Results
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border bg-muted/30 p-4">
            <p className="text-sm font-medium mb-3">Simulated Execution Results:</p>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span>Added:</span>
                <span className="font-medium text-green-600">+{result.added}</span>
              </div>
              <div className="flex justify-between">
                <span>Removed:</span>
                <span className="font-medium text-red-600">-{result.removed}</span>
              </div>
              <div className="flex justify-between">
                <span>Modified:</span>
                <span className="font-medium text-blue-600">~{result.modified}</span>
              </div>
              {hasConflicts && (
                <div className="flex justify-between">
                  <span>Conflicts:</span>
                  <span className="font-medium text-orange-600">!{result.conflicts}</span>
                </div>
              )}
            </div>
          </div>

          {hasConflicts && (
            <div className="rounded-lg bg-orange-50 border border-orange-200 p-3 flex gap-2">
              <AlertTriangle className="h-5 w-5 text-orange-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-orange-800">
                <p className="font-medium">Conflicts Detected</p>
                <p className="mt-1">
                  {result.conflicts} conflict(s) found. The selected strategy will handle these
                  accordingly.
                </p>
              </div>
            </div>
          )}

          <div className="text-sm text-muted-foreground text-center">
            Proceed with actual execution?
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button onClick={onConfirmExecute}>Confirm Execute</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
