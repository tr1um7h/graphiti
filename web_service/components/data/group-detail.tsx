'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import { Download, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { GroupDetail as GroupDetailType } from '@/lib/types';

interface GroupDetailProps {
  groupId: string;
}

const TABLE_NAMES = [
  'entity_nodes',
  'episodic_nodes',
  'community_nodes',
  'saga_nodes',
  'entity_edges',
  'episodic_edges',
  'community_edges',
  'has_episode_edges',
  'next_episode_edges',
];

export function GroupDetail({ groupId }: GroupDetailProps) {
  const [detail, setDetail] = useState<GroupDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchDetail = useCallback(
    async (table?: string, pageNum = 1) => {
      try {
        setLoading(true);
        const params = new URLSearchParams();
        if (table) {
          params.set('table', table);
          params.set('page', pageNum.toString());
          params.set('size', pageSize.toString());
        }
        const res = await fetch(
          `/api/data/groups/${encodeURIComponent(groupId)}${params.toString() ? `?${params}` : ''}`,
          { cache: 'no-store' }
        );
        if (!res.ok) throw new Error('Failed to fetch group detail');
        const data = await res.json();
        setDetail(data);
      } catch (error) {
        console.error('Failed to fetch group detail:', error);
      } finally {
        setLoading(false);
      }
    },
    [groupId]
  );

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleExpandTable = (tableName: string) => {
    if (expandedTable === tableName) {
      setExpandedTable(null);
    } else {
      setExpandedTable(tableName);
      setPage(1);
      fetchDetail(tableName, 1);
    }
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    if (expandedTable) {
      fetchDetail(expandedTable, newPage);
    }
  };

  const handleExport = async () => {
    try {
      const res = await fetch(
        `/api/data/groups/${encodeURIComponent(groupId)}/export`
      );
      if (!res.ok) throw new Error('Export failed');

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${groupId}_export.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Export failed:', error);
      alert('导出失败');
    }
  };

  if (loading && !detail) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        加载中...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
        分组不存在
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-semibold">分组：{groupId}</h3>
        <Button variant="outline" size="sm" onClick={handleExport}>
          <Download className="h-4 w-4 mr-2" />
          导出数据
        </Button>
      </div>

      <div className="rounded-lg border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-sm font-medium">
                  表名
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium">
                  记录数
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {TABLE_NAMES.map((tableName) => {
                const count = detail.table_counts[tableName] || 0;
                const isExpanded = expandedTable === tableName;

                return (
                  <Fragment key={tableName}>
                    <tr
                      className="border-b last:border-0 hover:bg-muted/30"
                    >
                      <td className="px-4 py-3">
                        <span className="font-medium">{tableName}</span>
                      </td>
                      <td className="px-4 py-3 text-right text-sm">
                        {count.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                          onClick={() => handleExpandTable(tableName)}
                        >
                          {isExpanded ? (
                            <>
                              收起 <ChevronUp className="h-3 w-3" />
                            </>
                          ) : (
                            <>
                              展开 <ChevronDown className="h-3 w-3" />
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-muted/20">
                        <td colSpan={3} className="px-4 py-4">
                          <div className="space-y-3">
                            {loading ? (
                              <p className="text-sm text-muted-foreground text-center py-4">
                                加载中...
                              </p>
                            ) : detail.records && detail.records.length > 0 ? (
                              <>
                                <div className="overflow-x-auto max-h-96">
                                  <table className="w-full text-xs">
                                    <thead>
                                      <tr className="border-b">
                                        {Object.keys(detail.records[0]).map(
                                          (key) => (
                                            <th
                                              key={key}
                                              className="px-2 py-1 text-left font-medium whitespace-nowrap"
                                            >
                                              {key}
                                            </th>
                                          )
                                        )}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.records.map((record, idx) => (
                                        <tr key={idx} className="border-b">
                                          {Object.values(record).map(
                                            (value, vidx) => (
                                              <td
                                                key={vidx}
                                                className="px-2 py-1 max-w-xs truncate"
                                                title={String(value)}
                                              >
                                                {JSON.stringify(value)}
                                              </td>
                                            )
                                          )}
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                                <div className="flex items-center justify-between text-sm">
                                  <span className="text-muted-foreground">
                                    第 {detail.page} 页，共{' '}
                                    {Math.ceil(detail.total / pageSize)} 页
                                  </span>
                                  <div className="flex gap-2">
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      disabled={page <= 1}
                                      onClick={() => handlePageChange(page - 1)}
                                    >
                                      上一页
                                    </Button>
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      disabled={
                                        page >= Math.ceil(detail.total / pageSize)
                                      }
                                      onClick={() => handlePageChange(page + 1)}
                                    >
                                      下一页
                                    </Button>
                                  </div>
                                </div>
                              </>
                            ) : (
                              <p className="text-sm text-muted-foreground text-center py-4">
                                暂无记录
                              </p>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
