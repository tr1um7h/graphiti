// components/chat/chat-floating-button.tsx
'use client';

import { useChatStore } from '@/stores/chat-store';
import { MessageCircle } from 'lucide-react';

export function ChatFloatingButton() {
  const isOpen = useChatStore((s) => s.isOpen);
  const toggle = useChatStore((s) => s.toggle);

  if (isOpen) return null;

  return (
    <button
      onClick={toggle}
      className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 active:scale-95"
      aria-label="打开对话"
    >
      <MessageCircle className="h-6 w-6" />
    </button>
  );
}