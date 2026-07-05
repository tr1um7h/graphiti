'use client';

import { Database, Clock, Eye, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { GroupStats } from '@/lib/types';

interface GroupsTableProps {
  groups: GroupStats[];
  onSelect: (groupId: string) => void;
  onDelete: (groupId: string) => void;
  deleting: string | null;
}

export function GroupsTable({ groups, onSelect, onDelete, deleting }: GroupsTableProps) {
  if (groups.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        <Database className="mx-auto h-12 w-12 mb-4 opacity-50" />
        <p className="text-sm font-medium">暂无分组</p>
        <p className="text-sm mt-2">导入数据以创建第一个分组</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Group ID</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">节点数</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">边数</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">创建时间</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">操作</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr
                key={group.group_id}
                className="border-b last:border-0 hover:bg-muted/30 transition-colors"
              >
                <td className="px-4 py-3">
                  <button
                    className="flex items-center gap-2 hover:text-primary transition-colors"
                    onClick={() => onSelect(group.group_id)}
                  >
                    <Database className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium underline-offset-2 hover:underline">
                      {group.group_id}
                    </span>
                  </button>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {group.node_count.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {group.edge_count.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {group.created_at ? (
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(group.created_at).toLocaleDateString()}
                    </div>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(group.group_id);
                      }}
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      disabled={deleting === group.group_id}
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(group.group_id);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}