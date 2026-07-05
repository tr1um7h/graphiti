'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Upload } from 'lucide-react';

interface ImportDataDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: () => void;
}

export function ImportDataDialog({ open, onOpenChange, onImported }: ImportDataDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [newGroupId, setNewGroupId] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setError(null);
    }
  };

  const handleImport = async () => {
    if (!file || !newGroupId.trim()) {
      setError('Please select a file and enter a group ID');
      return;
    }

    setImporting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('new_group_id', newGroupId.trim());
      formData.append('overwrite', overwrite.toString());

      const res = await fetch('/api/data/import', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Import failed' }));
        throw new Error(err.error || err.detail || 'Import failed');
      }

      const result = await res.json();
      console.log('Import successful:', result);
      onImported();
      setFile(null);
      setNewGroupId('');
      setOverwrite(false);
    } catch (err) {
      console.error('Import failed:', err);
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.name.endsWith('.zip')) {
      setFile(droppedFile);
      setError(null);
    } else {
      setError('Please drop a ZIP file');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import Data</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* File upload area */}
          <div>
            <Label>Upload ZIP Export</Label>
            <div
              className="mt-2 border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => document.getElementById('file-input')?.click()}
            >
              <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
              {file ? (
                <p className="text-sm">{file.name}</p>
              ) : (
                <>
                  <p className="text-sm font-medium">Click to select or drop file here</p>
                  <p className="text-xs text-muted-foreground mt-1">ZIP file required</p>
                </>
              )}
              <input
                id="file-input"
                type="file"
                accept=".zip"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>
          </div>

          {/* New Group ID */}
          <div>
            <Label htmlFor="new-group-id">New Group ID</Label>
            <Input
              id="new-group-id"
              value={newGroupId}
              onChange={(e) => setNewGroupId(e.target.value)}
              placeholder="my_new_group"
              className="mt-2"
            />
          </div>

          {/* Overwrite checkbox */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="overwrite"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              className="rounded border-gray-300"
            />
            <Label htmlFor="overwrite" className="text-sm font-normal">
              Overwrite if group already exists
            </Label>
          </div>

          {/* Error message */}
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
            <Button onClick={handleImport} disabled={importing || !file || !newGroupId.trim()}>
              {importing ? 'Importing...' : 'Import'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
