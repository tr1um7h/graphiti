'use client';

import dynamic from 'next/dynamic';

const MemorySchemaClient = dynamic(() => import('./memory-schema-client'), {
  ssr: false,
});

export default function MemorySchemaPage() {
  return <MemorySchemaClient />;
}
