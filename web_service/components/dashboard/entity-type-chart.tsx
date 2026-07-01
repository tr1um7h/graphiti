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
import { NODE_COLORS } from '@/lib/graph-theme';

interface NodeTypeData {
  type: string;
  count: number;
}

interface EntityTypeChartProps {
  data: NodeTypeData[];
}

export function EntityTypeChart({ data }: EntityTypeChartProps) {
  // 防御性编程：如果 data 为 undefined 或空，返回空数组
  const safeData = data || [];
  const total = safeData.reduce((sum, d) => sum + d.count, 0);

  const chartData = safeData.map((d) => ({
    name: d.type,
    count: d.count,
    percent: total > 0 ? ((d.count / total) * 100).toFixed(1) : '0',
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Entity Type Distribution</CardTitle>
      </CardHeader>
      <CardContent>
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
                width={80}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                formatter={(value, _name, props) => [
                  `${value} (${(props as { payload: { percent: string } }).payload.percent}%)`,
                  'Count',
                ]}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={20}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={NODE_COLORS[entry.name] || NODE_COLORS['default']}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
