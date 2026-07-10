// components/chat/chat-drawer.tsx
'use client';

import { useEffect, useRef } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { ChatMessageBubble } from '@/components/chat/chat-message';
import { ChatInput } from '@/components/chat/chat-input';
import { X, RefreshCw, Loader2 } from 'lucide-react';

export function ChatDrawer() {
  const isOpen = useChatStore((s) => s.isOpen);
  const messages = useChatStore((s) => s.messages);
  const isLoading = useChatStore((s) => s.isLoading);
  const error = useChatStore((s) => s.error);
  const context = useChatStore((s) => s.context);
  const close = useChatStore((s) => s.close);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const retry = useChatStore((s) => s.retry);

  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const contextLabel = context.context_name
    ? `${
        context.context_type === 'node'
          ? '节点'
          : context.context_type === 'edge'
            ? '边'
            : context.context_type === 'document'
              ? '文档'
              : '分组'
      }: ${context.context_name}`
    : context.context_id
      ? `当前上下文: ${context.context_id}`
      : '当前上下文: 无';

  return (
    <div
      className={`flex flex-col border-l bg-background transition-all duration-200 ease-in-out ${
        isOpen ? 'w-[400px]' : 'w-0 overflow-hidden border-l-0'
      }`}
    >
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <h2 className="text-sm font-semibold">Chat</h2>
        <button
          onClick={clearMessages}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="新对话"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
        <div className="flex-1" />
        <button
          onClick={close}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Context badge */}
      <div className="border-b px-4 py-1.5">
        <span className="text-xs text-muted-foreground">{contextLabel}</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {messages.length === 0 && !isLoading && (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">
              向知识图谱提问，验证数据抽取是否完整...
            </p>
          </div>
        )}

        <div className="space-y-3">
          {messages.map((msg) => (
            <ChatMessageBubble key={msg.id} message={msg} />
          ))}

          {isLoading && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-muted px-4 py-2">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2">
              <p className="text-xs text-destructive">{error}</p>
              <button
                onClick={retry}
                className="mt-1 text-xs font-medium text-destructive underline"
              >
                重试
              </button>
            </div>
          )}
        </div>

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <ChatInput />
    </div>
  );
}