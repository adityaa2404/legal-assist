import React from 'react';
import { cn } from '@/lib/utils';

interface IconProps {
  name: string;
  className?: string;
  filled?: boolean;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

const sizeMap = {
  sm: 'text-sm',
  md: 'text-lg',
  lg: 'text-2xl',
  xl: 'text-4xl',
};

const Icon: React.FC<IconProps> = ({ name, className, filled = false, size = 'md' }) => (
  <span
    className={cn('material-symbols-outlined', sizeMap[size], className)}
    style={filled ? { fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24" } : undefined}
  >
    {name}
  </span>
);

export default Icon;
