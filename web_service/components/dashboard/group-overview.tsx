'use client';

import Link from 'next/link';
import { Layers } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface GroupData {
  id: string;
  name: string;
  count: number;
}

interface GroupOverviewProps {
  groups: GroupData[];
}

export function GroupOverview({ groups }: GroupOverviewProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Group Overview</CardTitle>
      </CardHeader>
      <CardContent>
        {(!groups || groups.length === 0) ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No groups available
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {groups.map((g) => (
              <Link
                key={g.id || g.name}
                href={`/documents`}
                className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3 transition-colors hover:bg-muted"
              >
                <div className="rounded-md bg-primary/10 p-2">
                  <Layers className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">
                    {g.name || g.id || 'unnamed'}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {g.count} 节点
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
