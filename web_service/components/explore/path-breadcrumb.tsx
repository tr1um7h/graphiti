'use client';

import { ChevronRight } from 'lucide-react';

interface PathItem {
  id: string;
  name: string;
  type: string;
}

interface PathBreadcrumbProps {
  path: PathItem[];
  onNavigate: (index: number) => void;
}

export default function PathBreadcrumb({ path, onNavigate }: PathBreadcrumbProps) {
  if (path.length === 0) return null;

  return (
    <nav className="flex items-center gap-1 text-sm">
      {path.map((item, index) => (
        <span key={index} className="flex items-center gap-1">
          {index > 0 && (
            <ChevronRight className="size-3 text-muted-foreground" />
          )}
          <button
            onClick={() => onNavigate(index)}
            className={`rounded px-1.5 py-0.5 transition-colors ${
              index === path.length - 1
                ? 'font-medium text-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent'
            }`}
          >
            {item.name}
          </button>
        </span>
      ))}
    </nav>
  );
}
