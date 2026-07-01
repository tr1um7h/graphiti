import { StatsCards } from '@/components/dashboard/stats-cards';
import { RelationTypeChart } from '@/components/dashboard/relation-type-chart';
import { GroupOverview } from '@/components/dashboard/group-overview';
import { RecentActivity, type ActivityItem } from '@/components/dashboard/recent-activity';
import type { GraphStats } from '@/lib/types';

interface GroupData {
  id: string;
  name: string;
  count: number;
}

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
  const [stats, groups, timeline] = await Promise.all([
    fetchJson<GraphStats>('/api/graph/stats'),
    fetchJson<GroupData[]>('/api/graph/groups'),
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
          totalDocuments: stats?.totalDocuments ?? 0,
          totalGroups: groups?.length ?? 0,
          todayNewNodes: stats?.todayNewNodes ?? 0,
          todayNewEdges: stats?.todayNewEdges ?? 0,
          todayNewDocuments: stats?.todayNewDocuments ?? 0,
        }}
      />

      {/* Charts + Activity side by side */}
      <div className="grid gap-6 lg:grid-cols-2">
        <RelationTypeChart data={stats?.edgeTypes || []} />
        <RecentActivity activities={activities} />
      </div>

      {/* Group Overview */}
      <GroupOverview groups={groups || []} />
    </div>
  );
}
