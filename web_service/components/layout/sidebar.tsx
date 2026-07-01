'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  Network,
  FolderOpen,
  Menu,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from '@/components/ui/sheet';
import { cn } from '@/lib/utils';

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  {
    label: 'Overview',
    href: '/',
    icon: <BarChart3 className="h-4 w-4" />,
  },
  {
    label: 'Graph',
    href: '/graph',
    icon: <Network className="h-4 w-4" />,
  },
  {
    label: 'Documents',
    href: '/documents',
    icon: <FolderOpen className="h-4 w-4" />,
  },
];

function SidebarContent() {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-14 items-center border-b px-4">
        <span className="text-lg font-bold">Graphiti</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => (
          <Link
            key={item.label}
            href={item.href}
            className={cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground',
              pathname === item.href
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground'
            )}
          >
            {item.icon}
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function Sidebar() {
  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex h-screen w-48 flex-col border-r bg-background">
        <SidebarContent />
      </aside>

      {/* Mobile sidebar */}
      <div className="lg:hidden fixed top-0 left-0 z-40 p-2">
        <Sheet>
          <SheetTrigger
            render={(props) => (
              <Button variant="ghost" size="icon" {...props}>
                <Menu className="h-5 w-5" />
              </Button>
            )}
          />
          <SheetContent side="left" className="w-48 p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SidebarContent />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
