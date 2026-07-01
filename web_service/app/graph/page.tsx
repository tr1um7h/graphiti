// app/graph/page.tsx
'use client';

import dynamic from 'next/dynamic';

const GraphPageClient = dynamic(() => import('./graph-client'), {
  ssr: false,
});

export default function GraphPage() {
  return <GraphPageClient />;
}
