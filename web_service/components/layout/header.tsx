'use client';

import { usePathname } from 'next/navigation';
import { Badge } from '@/components/ui/badge';

const routeTitles: Record<string, string> = {
  '/': 'Overview',
  '/graph': 'Graph',
  '/explore': 'Explore',
  '/documents': 'Documents',
  '/settings': 'Settings',
};

export function Header() {
  const pathname = usePathname();
  const title = routeTitles[pathname] || 'Graphiti';

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <h1 className="text-lg font-semibold">{title}</h1>
      <Badge variant="secondary" className="text-xs">
        Beta
      </Badge>
    </header>
  );
}
