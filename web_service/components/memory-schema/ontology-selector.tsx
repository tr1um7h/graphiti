'use client';

import { useOntologyStore } from '@/stores/ontology-store';

export function OntologySelector() {
  const groups = useOntologyStore((s) => s.groups);
  const selectedGroupId = useOntologyStore((s) => s.selectedGroupId);
  const setSelectedGroupId = useOntologyStore((s) => s.setSelectedGroupId);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value === 'all') {
      setSelectedGroupId(null);
    } else {
      setSelectedGroupId(value);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <select
        value={selectedGroupId ?? 'all'}
        onChange={handleChange}
        className="flex h-9 w-[200px] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <option value="all">All Groups</option>
        {groups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name} ({g.episode_count} ep / {g.entity_count} ent)
          </option>
        ))}
      </select>
    </div>
  );
}
