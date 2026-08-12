// stores/ontology-store.ts
import { create } from 'zustand';
import type { MemorySchemaData, SchemaEdge } from '@/lib/types';

export interface GraphGroup {
  id: string;
  name: string;
  episode_count: number;
  entity_count: number;
}

interface OntologyState {
  schemaData: MemorySchemaData | null;
  groups: GraphGroup[];
  selectedGroupId: string | null;
  focusedItemId: string | null;
  relatedItemIds: Set<string>;
  scale: number;
  loading: boolean;
  error: string | null;

  setGroups: (groups: GraphGroup[]) => void;
  setSelectedGroupId: (id: string | null) => void;
  setSchemaData: (data: MemorySchemaData) => void;
  setFocusedItem: (itemId: string | null) => void;
  setScale: (scale: number) => void;
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
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  clearFocus: () => set({ focusedItemId: null, relatedItemIds: new Set() }),
}));