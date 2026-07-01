'use client';

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import NodeDetailTab from './node-detail-tab';
import AgentChatTab from './agent-chat-tab';

interface RightPanelProps {
  selectedNodeId: string | null;
  centerEntityId: string;
  centerEntityName?: string;
  visibleNodeIds: string[];
  onNavigateToNode?: (id: string) => void;
  onHighlightNodes?: (nodeIds: string[]) => void;
}

export default function RightPanel({
  selectedNodeId,
  centerEntityId,
  centerEntityName,
  visibleNodeIds,
  onNavigateToNode,
  onHighlightNodes,
}: RightPanelProps) {
  return (
    <Tabs defaultValue="detail" className="flex h-full flex-col">
      <TabsList className="mx-3 mt-2">
        <TabsTrigger value="detail">节点详情</TabsTrigger>
        <TabsTrigger value="chat">AI 助手</TabsTrigger>
      </TabsList>

      <TabsContent value="detail" className="flex-1 overflow-hidden">
        <NodeDetailTab
          nodeId={selectedNodeId}
          onNavigateToNode={onNavigateToNode}
        />
      </TabsContent>

      <TabsContent value="chat" className="flex-1 overflow-hidden">
        <AgentChatTab
          centerEntityId={centerEntityId}
          centerEntityName={centerEntityName}
          visibleNodeIds={visibleNodeIds}
          onHighlightNodes={onHighlightNodes}
        />
      </TabsContent>
    </Tabs>
  );
}
