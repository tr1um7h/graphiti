'use client';

import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Upload, Link } from 'lucide-react';

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fired the moment an upload/import request succeeds; the page uses it to
   *  add an optimistic placeholder and start polling until the doc lands. */
  onUploaded?: (name: string) => void;
}

export function UploadDialog({ open, onOpenChange, onUploaded }: UploadDialogProps) {
  const [url, setUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;
      setUploading(true);
      setUploadResult(null);
      try {
        for (const file of acceptedFiles) {
          const formData = new FormData();
          formData.append('file', file);
          const res = await fetch('/api/documents/upload', { method: 'POST', body: formData });
          if (!res.ok) {
            const err = await res.json().catch(() => ({ error: 'Upload failed' }));
            throw new Error(err.error || 'Upload failed');
          }
          const result = await res.json();
          setUploadResult(`✓ ${result.name} uploaded successfully`);
          // Hand off to the page: it shows the in-flight task and polls until committed.
          onUploaded?.(file.name);
        }
      } catch (error) {
        setUploadResult(`✗ Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        setUploading(false);
      }
    },
    [onUploaded],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
    },
    disabled: uploading,
  });

  const handleUrlImport = async () => {
    if (!url.trim()) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Import failed' }));
        throw new Error(err.error || 'Import failed');
      }
      const result = await res.json();
      setUploadResult(`✓ ${result.name} imported successfully`);
      setUrl('');
      onUploaded?.(result.name);
    } catch (error) {
      setUploadResult(`✗ Import failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    setUploadResult(null);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Upload Files</DialogTitle>
        </DialogHeader>

        {/* Drag and drop area */}
        <div
          {...getRootProps()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
            isDragActive
              ? 'border-primary bg-primary/5'
              : 'border-muted-foreground/25 hover:border-primary/50'
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {uploading ? 'Uploading...' : isDragActive ? 'Drop files here...' : 'Drag files here or click to select'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">Supports PDF, DOCX, TXT, MD</p>
        </div>

        {/* Upload result feedback */}
        {uploadResult && (
          <p className={`text-sm ${
            uploadResult.startsWith('✓') ? 'text-green-600' : 'text-red-500'
          }`}>
            {uploadResult}
          </p>
        )}

        {/* Dataset selector placeholder */}
        <div className="space-y-2">
          <Label htmlFor="dataset">Target Dataset</Label>
          <Input id="dataset" value="Default Dataset" disabled />
        </div>

        {/* URL import */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">or import from URL</span>
            <Separator className="flex-1" />
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="https://example.com/document.pdf"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={uploading}
            />
            <Button variant="outline" onClick={handleUrlImport} disabled={uploading || !url.trim()}>
              <Link className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
