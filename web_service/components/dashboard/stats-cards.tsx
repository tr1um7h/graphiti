'use client';

import Link from 'next/link';
import { Network, ArrowLeftRight, FileText, MessageSquare } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

interface StatCard {
  label: string;
  value: number;
  todayNew: number;
  icon: React.ReactNode;
  href: string;
}

interface StatsCardsProps {
  stats: {
    totalNodes: number;
    totalEdges: number;
    totalDocuments: number;
    totalConversations: number;
    todayNewNodes: number;
    todayNewEdges: number;
    todayNewDocuments: number;
    todayNewConversations: number;
  };
}

const cards: (Omit<StatCard, 'value' | 'todayNew'> & { key: string })[] = [
  { key: 'nodes', label: '实体', icon: <Network className="h-5 w-5 text-blue-500" />, href: '/graph' },
  { key: 'edges', label: '关系', icon: <ArrowLeftRight className="h-5 w-5 text-green-500" />, href: '/graph' },
  { key: 'documents', label: '文档', icon: <FileText className="h-5 w-5 text-orange-500" />, href: '/documents' },
  { key: 'conversations', label: '对话轮', icon: <MessageSquare className="h-5 w-5 text-purple-500" />, href: '/explore' },
];

export function StatsCards({ stats }: StatsCardsProps) {
  const values: Record<string, { value: number; todayNew: number }> = {
    nodes: { value: stats.totalNodes, todayNew: stats.todayNewNodes },
    edges: { value: stats.totalEdges, todayNew: stats.todayNewEdges },
    documents: { value: stats.totalDocuments, todayNew: stats.todayNewDocuments },
    conversations: { value: stats.totalConversations, todayNew: stats.todayNewConversations },
  };

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Link key={card.key} href={card.href}>
          <Card className="transition-shadow hover:shadow-md cursor-pointer">
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-lg bg-muted p-2.5">
                {card.icon}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-2xl font-bold">
                  {values[card.key].value.toLocaleString()}
                </div>
                <div className="text-sm text-muted-foreground">{card.label}</div>
                <div className="text-xs text-emerald-600">
                  +{values[card.key].todayNew} 今日
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
