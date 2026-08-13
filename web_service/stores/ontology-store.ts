// stores/ontology-store.ts
import { create } from 'zustand';
import type { MemorySchemaData, SchemaEdge } from '@/lib/types';

export interface GraphGroup {
  id: string;
  name: string;
  episode_count: number;
  entity_count: number;
}

const MIN_SCALE = 0.1;
const MAX_SCALE = 1.6;
const FIT_PADDING = 48;

function clampScale(value: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
}

interface OntologyState {
  schemaData: MemorySchemaData | null;
  groups: GraphGroup[];
  selectedGroupId: string | null;
  focusedItemId: string | null;
  relatedItemIds: Set<string>;
  scale: number;
  panX: number;
  panY: number;
  loading: boolean;
  error: string | null;

  setGroups: (groups: GraphGroup[]) => void;
  setSelectedGroupId: (id: string | null) => void;
  setSchemaData: (data: MemorySchemaData) => void;
  setFocusedItem: (itemId: string | null) => void;
  setScale: (scale: number) => void;
  setPan: (x: number, y: number) => void;
  zoomBy: (delta: number) => void;
  fitView: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearFocus: () => void;
}

/** Compute all item IDs connected to a given item via edges */
function computeRelatedItems(itemId: string, edges: SchemaEdge[]): Set<string> {
  const related = new Set<string>();
  for (const edge of edges) {
    if (edge.source === itemId) related.add(edge.target);
    if (edge.target === itemId) related.add(edge.source);
  }
  return related;
}

export const useOntologyStore = create<OntologyState>((set, get) => ({
  schemaData: null,
  groups: [],
  selectedGroupId: null,
  focusedItemId: null,
  relatedItemIds: new Set(),
  scale: 1,
  panX: 0,
  panY: 0,
  loading: false,
  error: null,

  setGroups: (groups) => set({ groups }),
  setSelectedGroupId: (id) => set({ selectedGroupId: id }),
  setSchemaData: (data) => set({ schemaData: data }),
  setFocusedItem: (itemId) => {
    if (!itemId) {
      set({ focusedItemId: null, relatedItemIds: new Set() });
      return;
    }
    const schemaData = get().schemaData;
    const related: Set<string> = schemaData ? computeRelatedItems(itemId, schemaData.edges) : new Set();
    set({ focusedItemId: itemId, relatedItemIds: related });
  },
  setScale: (scale) => set({ scale }),
  setPan: (panX, panY) => set({ panX, panY }),
  zoomBy: (delta) => {
    const state = get();
    const nextScale = clampScale(state.scale + delta);
    if (nextScale === state.scale) return;

    const viewport = document.querySelector<HTMLElement>('[data-memory-canvas-viewport]');
    const rect = viewport?.getBoundingClientRect();
    const centerX = rect?.width ? rect.width / 2 : window.innerWidth / 2;
    const centerY = rect?.height ? rect.height / 2 : window.innerHeight / 2;
    const ratio = nextScale / state.scale;

    set({
      scale: nextScale,
      panX: centerX - (centerX - state.panX) * ratio,
      panY: centerY - (centerY - state.panY) * ratio,
    });
  },
  fitView: () => {
    const host = document.querySelector<HTMLElement>('[data-memory-canvas-transform]');
    const content = document.querySelector<HTMLElement>('[data-memory-canvas-content]');
    const viewport = document.querySelector<HTMLElement>('[data-memory-canvas-viewport]');
    if (!host || !content || !viewport) return;

    const hostRect = host.getBoundingClientRect();
    const scaleRatio =
      hostRect.width && host.clientWidth ? hostRect.width / host.clientWidth : 1;
    const cardRects = Array.from(content.querySelectorAll<HTMLElement>('[data-memory-card]'))
      .map((el) => el.getBoundingClientRect())
      .filter((rect) => rect.width > 0 && rect.height > 0);

    let left: number;
    let top: number;
    let right: number;
    let bottom: number;

    if (cardRects.length > 0) {
      left = Math.min(...cardRects.map((rect) => rect.left));
      top = Math.min(...cardRects.map((rect) => rect.top));
      right = Math.max(...cardRects.map((rect) => rect.right));
      bottom = Math.max(...cardRects.map((rect) => rect.bottom));
    } else {
      const contentRect = content.getBoundingClientRect();
      left = contentRect.left;
      top = contentRect.top;
      right = contentRect.right;
      bottom = contentRect.bottom;
    }

    const contentLeft = (left - hostRect.left) / scaleRatio - FIT_PADDING;
    const contentTop = (top - hostRect.top) / scaleRatio - FIT_PADDING;
    const contentWidth = Math.max(1, (right - left) / scaleRatio + FIT_PADDING * 2);
    const contentHeight = Math.max(1, (bottom - top) / scaleRatio + FIT_PADDING * 2);
    const viewportRect = viewport.getBoundingClientRect();
    const nextScale = Math.min(
      1,
      viewportRect.width / contentWidth,
      viewportRect.height / contentHeight
    );

    set({
      scale: nextScale,
      panX: (viewportRect.width - contentWidth * nextScale) / 2 - contentLeft * nextScale,
      panY: (viewportRect.height - contentHeight * nextScale) / 2 - contentTop * nextScale,
    });
  },
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  clearFocus: () => set({ focusedItemId: null, relatedItemIds: new Set() }),
}));
