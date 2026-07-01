'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Bot } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import ChatMessage from './chat-message';
import ChatInput from './chat-input';
import type { ExploreChatResponse } from '@/lib/types';

interface AgentChatTabProps {
  centerEntityId: string;
  centerEntityName?: string;
  visibleNodeIds: string[];
  onHighlightNodes?: (nodeIds: string[]) => void;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export default function AgentChatTab({
  centerEntityId,
  centerEntityName,
  visibleNodeIds,
  onHighlightNodes,
}: AgentChatTabProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Add context message when center entity changes
  useEffect(() => {
    if (!centerEntityId) return;
    const contextMsg: Message = {
      id: `ctx-${centerEntityId}`,
      role: 'assistant',
      content: centerEntityName
        ? `当前探索实体：**${centerEntityName}**\n\n您可以询问关于该实体的关系、属性等问题。`
        : '请选择一个实体开始探索。',
    };
    setMessages([contextMsg]);
  }, [centerEntityId, centerEntityName]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(
    async (text: string) => {
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);

      try {
        const res = await fetch('/api/explore/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            centerEntityId,
            visibleNodeIds,
          }),
        });

        const data: ExploreChatResponse = await res.json();

        const assistantMsg: Message = {
          id: `asst-${Date.now()}`,
          role: 'assistant',
          content: data.answer,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        // Handle highlight nodes
        if (data.highlightNodes && data.highlightNodes.length > 0) {
          onHighlightNodes?.(data.highlightNodes);
        }
      } catch {
        const errMsg: Message = {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: '抱歉，请求出错了，请稍后重试。',
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        setLoading(false);
      }
    },
    [centerEntityId, visibleNodeIds, onHighlightNodes],
  );

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="flex-1 p-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-muted-foreground">
            <Bot className="size-8" />
            <p className="text-sm">AI 助手</p>
            <p className="text-xs">选择实体后开始对话</p>
          </div>
        )}
        <div className="flex flex-col gap-3">
          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              role={msg.role}
              content={msg.content}
              onHighlight={onHighlightNodes}
            />
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary">
                <Bot className="size-4 animate-pulse" />
              </div>
              <div className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                思考中...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
      <ChatInput onSend={sendMessage} disabled={loading || !centerEntityId} />
    </div>
  );
}
