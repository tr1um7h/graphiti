import { StatsCards } from '@/components/dashboard/stats-cards';
import { EntityTypeChart } from '@/components/dashboard/entity-type-chart';
import { RecentActivity, type ActivityItem } from '@/components/dashboard/recent-activity';
import { DocumentStatusChart } from '@/components/dashboard/document-status-chart';
import type { GraphStats } from '@/lib/types';
import type { Document } from '@/lib/types';

const BASE_URL = 'http://localhost:3000';

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE_URL}${path}`, { cache: 'no-store' });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function DashboardPage() {
  const [stats, documents, timeline] = await Promise.all([
    fetchJson<GraphStats>('/api/graph/stats'),
    fetchJson<Document[]>('/api/documents'),
    fetchJson<ActivityItem[]>('/api/graph/timeline?limit=6'),
  ]);
  
  // 将 Server 返回的 timeline 数据转换为 ActivityItem 格式
  const activities: ActivityItem[] = (timeline || []).map((item, index) => ({
    id: `t${index}`,
    description: item.description,
    source: item.source || 'graphiti',
    time: item.time,
  }));

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Knowledge Graph Overview</h2>

      {/* Stats Cards */}
      <StatsCards
        stats={{
          totalNodes: stats?.totalNodes ?? 0,
          totalEdges: stats?.totalEdges ?? 0,
          totalDocuments: documents?.length ?? 0,
          totalConversations: 42,
          todayNewNodes: stats?.todayNewNodes ?? 0,
          todayNewEdges: stats?.todayNewEdges ?? 0,
          todayNewDocuments: 3,
          todayNewConversations: 5,
        }}
      />

      {/* Charts + Activity side by side */}
      <div className="grid gap-6 lg:grid-cols-2">
        {stats && <EntityTypeChart data={stats.nodeTypes || []} />}
        <RecentActivity activities={activities.length > 0 ? activities : []} />
      </div>

      {/* Document Status Chart */}
      {documents && <DocumentStatusChart documents={documents} />}
    </div>
  );
}
