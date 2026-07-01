'use client';

import { Trash2, Eye } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Document, DocumentStatus } from '@/lib/types';

const statusConfig: Record<DocumentStatus, { label: string; emoji: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  completed: { label: '已处理', emoji: '✅', variant: 'default' },
  processing: { label: '处理中', emoji: '🔄', variant: 'secondary' },
  pending: { label: '排队中', emoji: '⏳', variant: 'outline' },
  failed: { label: '失败', emoji: '❌', variant: 'destructive' },
};

const typeVariant: Record<string, 'default' | 'secondary' | 'outline'> = {
  PDF: 'default',
  DOCX: 'secondary',
  MD: 'outline',
  TXT: 'outline',
  URL: 'secondary',
};

interface DocumentTableProps {
  documents: Document[];
  onDelete?: (doc: Document) => void;
}

export function DocumentTable({ documents, onDelete }: DocumentTableProps) {
  return (
    <div className="rounded-lg border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">文件名</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">类型</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">状态</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">实体数</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">操作</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  暂无文档
                </td>
              </tr>
            ) : (
              documents.map((doc) => {
                const status = statusConfig[doc.status];
                return (
                  <tr key={doc.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-medium">{doc.name}</td>
                    <td className="px-4 py-3">
                      <Badge variant={typeVariant[doc.type] || 'outline'}>{doc.type}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={status.variant}>
                        {status.emoji} {status.label}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {doc.entityCount > 0 ? doc.entityCount : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon-xs" onClick={() => window.location.href = `/documents/${doc.id}`}>
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          title={
                            doc.status === 'processing' || doc.status === 'pending'
                              ? 'Cannot delete while processing'
                              : 'Delete'
                          }
                          aria-label={`Delete ${doc.name}`}
                          disabled={doc.status === 'processing' || doc.status === 'pending'}
                          onClick={() => onDelete?.(doc)}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
