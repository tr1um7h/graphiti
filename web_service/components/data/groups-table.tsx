'use client';

import { Database, Clock } from 'lucide-react';
import type { GroupStats } from '@/lib/types';

interface GroupsTableProps {
  groups: GroupStats[];
  onSelect: (groupId: string) => void;
}

export function GroupsTable({ groups, onSelect }: GroupsTableProps) {
  if (groups.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        <Database className="mx-auto h-12 w-12 mb-4 opacity-50" />
        <p>No groups found</p>
        <p className="text-sm mt-2">Import data to create your first group</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-3 text-left text-sm font-medium">
                Group ID
              </th>
              <th className="px-4 py-3 text-left text-sm font-medium">
                Nodes
              </th>
              <th className="px-4 py-3 text-left text-sm font-medium">
                Edges
              </th>
              <th className="px-4 py-3 text-left text-sm font-medium">
                Created
              </th>
              <th className="px-4 py-3 text-right text-sm font-medium">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr
                key={group.group_id}
                className="border-b last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                onClick={() => onSelect(group.group_id)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Database className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">{group.group_id}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-sm">
                  {group.node_count.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-sm">
                  {group.edge_count.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {group.created_at ? (
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(group.created_at).toLocaleDateString()}
                    </div>
                  ) : (
                    '-'
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    className="text-sm text-primary hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect(group.group_id);
                    }}
                  >
                    View Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
