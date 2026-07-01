'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface StatusCount {
  status: string;
  emoji: string;
  label: string;
  count: number;
  color: string;
}

interface DocumentStatusChartProps {
  documents: { status: string }[];
}

export function DocumentStatusChart({ documents }: DocumentStatusChartProps) {
  const counts: Record<string, number> = {};
  for (const doc of documents) {
    counts[doc.status] = (counts[doc.status] || 0) + 1;
  }

  const statuses: StatusCount[] = [
    { status: 'completed', emoji: '✅', label: '已处理', count: counts['completed'] || 0, color: 'text-emerald-600' },
    { status: 'processing', emoji: '🔄', label: '处理中', count: counts['processing'] || 0, color: 'text-blue-600' },
    { status: 'pending', emoji: '⏳', label: '排队中', count: counts['pending'] || 0, color: 'text-yellow-600' },
    { status: 'failed', emoji: '❌', label: '失败', count: counts['failed'] || 0, color: 'text-red-600' },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Document Status</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {statuses.map((s) => (
            <div
              key={s.status}
              className="flex flex-col items-center rounded-lg border bg-muted/30 p-4"
            >
              <span className="text-2xl">{s.emoji}</span>
              <span className={`mt-1 text-2xl font-bold ${s.color}`}>{s.count}</span>
              <span className="text-xs text-muted-foreground">{s.label}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
