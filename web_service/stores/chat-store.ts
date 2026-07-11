// stores/chat-store.ts
'use client';

import { create } from 'zustand';
import type { ChatContext, ChatMessage, ChatRequest, ChatResponse } from '@/lib/types';

let _msgId = 0;
function nextId(): string {
  return `msg_${Date.now()}_${++_msgId}`;
}

interface ChatState {
  // UI
  isOpen: boolean;
  isFullscreen: boolean;

  // Conversation (in-memory only, lost on refresh)
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;

  // Context synced from graph page
  context: ChatContext;

  // Last user message content (for retry)
  _lastUserContent: string | null;

  // Actions
  toggle: () => void;
  open: (ctx?: ChatContext) => void;
  close: () => void;
  toggleFullscreen: () => void;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  setContext: (ctx: Partial<ChatContext>) => void;
  clearContext: () => void;
  retry: () => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  isOpen: false,
  isFullscreen: false,
  messages: [],
  isLoading: false,
  error: null,
  context: {},
  _lastUserContent: null,

  toggle: () => set((s) => ({ isOpen: !s.isOpen })),

  open: (ctx) =>
    set({
      isOpen: true,
      ...(ctx ? { context: { ...get().context, ...ctx } } : {}),
    }),

  close: () => set({ isOpen: false, isFullscreen: false }),

  toggleFullscreen: () => set((s) => ({ isFullscreen: !s.isFullscreen })),

  sendMessage: async (content: string) => {
    const { context } = get();
    const userMsg: ChatMessage = {
      id: nextId(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };

    set((s) => ({
      messages: [...s.messages, userMsg],
      isLoading: true,
      error: null,
      _lastUserContent: content,
    }));

    try {
      // Send all prior messages as history (exclude the user msg just added)
      const history = get().messages.slice(0, -1);

      const body: ChatRequest = {
        message: content,
        context,
        history,
      };

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        throw new Error(`Chat API error: ${res.status}`);
      }

      const data: ChatResponse = await res.json();

      const aiMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        content: data.answer,
        timestamp: Date.now(),
      };

      set((s) => ({
        messages: [...s.messages, aiMsg],
        isLoading: false,
        error: null,
      }));
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : '请求失败，请重试',
      });
    }
  },

  clearMessages: () => set({ messages: [], error: null, _lastUserContent: null }),

  setContext: (ctx) => set((s) => ({ context: { ...s.context, ...ctx } })),

  clearContext: () => set({ context: {} }),

  retry: async () => {
    const { _lastUserContent, messages } = get();
    if (!_lastUserContent) return;
    // Remove last assistant message (the failed one)
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') {
        set({ messages: messages.slice(0, i) });
        break;
      }
    }
    await get().sendMessage(_lastUserContent);
  },
}));