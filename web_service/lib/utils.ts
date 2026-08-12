// lib/utils.ts
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function itemLabel(i: { name?: string; content?: string; label?: string } | undefined): string {
  return i?.label ?? i?.name ?? i?.content ?? '';
}
