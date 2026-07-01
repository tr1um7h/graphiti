'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface EdgeTypeData {
  type: string;
  count: number;
}

interface RelationTypeChartProps {
  data: EdgeTypeData[];
}

// 调色板，用于不同关系类型的颜色区分
const COLORS = [
  '#3b82f6', '#22c55e', '#f97316', '#a855f7', '#06b6d4',
  '#ef4444', '#eab308', '#8b5cf6', '#14b8a6', '#ec4899',
];

export function RelationTypeChart({ data }: RelationTypeChartProps) {
  const safeData = (data || []).slice(0, 10);
  const total = safeData.reduce((sum, d) => sum + d.count, 0);

  const chartData = safeData.map((d) => ({
    name: d.type,
    count: d.count,
    percent: total > 0 ? ((d.count / total) * 100).toFixed(1) : '0',
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Relation Type Distribution</CardTitle>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <p className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
            No relationship data
          </p>
        ) : (
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 0, right: 40, left: 0, bottom: 0 }}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={120}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  formatter={(value, _name, props) => [
                    `${value} (${(props as { payload: { percent: string } }).payload.percent}%)`,
                    'Count',
                  ]}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={entry.name}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
