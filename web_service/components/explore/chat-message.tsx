'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  onHighlight?: (nodeIds: string[]) => void;
}

export default function ChatMessage({
  role,
  content,
  onHighlight,
}: ChatMessageProps) {
  const isAssistant = role === 'assistant';
  const hasHighlight = isAssistant && content.includes('高亮');

  return (
    <div className={`flex gap-3 ${isAssistant ? '' : 'flex-row-reverse'}`}>
      {/* Avatar */}
      <div
        className={`flex size-7 shrink-0 items-center justify-center rounded-full ${
          isAssistant ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
        }`}
      >
        {isAssistant ? <Bot className="size-4" /> : <User className="size-4" />}
      </div>

      {/* Message bubble */}
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
          isAssistant
            ? 'bg-muted/50 text-foreground'
            : 'bg-primary text-primary-foreground'
        }`}
      >
        {isAssistant ? (
          <div className="prose prose-sm prose-invert max-w-none [&_table]:text-xs [&_th]:px-2 [&_td]:px-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        ) : (
          <p>{content}</p>
        )}

        {hasHighlight && onHighlight && (
          <div className="mt-2 border-t border-border/40 pt-2">
            <Button
              variant="ghost"
              size="xs"
              onClick={() => onHighlight([])}
              className="gap-1"
            >
              <Sparkles className="size-3" />
              在图谱中高亮
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
